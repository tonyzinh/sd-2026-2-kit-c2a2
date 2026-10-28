import threading

import pytest
import requests
from fastapi.testclient import TestClient

from servicos.comum.circuit_breaker import CircuitBreaker, CircuitoAberto
from servicos.comum.retry import com_retentativas, e_transitorio
from servicos.geracao import app as ger


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def falha():
    raise ConnectionError("x")


def test_ciclo_completo_fechado_aberto_meio_fechado():
    rel = Relogio()
    cb = CircuitBreaker(limite_falhas=3, espera_segundos=20, relogio=rel)
    for _ in range(3):
        with pytest.raises(ConnectionError):
            cb.chamar(falha)
    assert cb.estado == "aberto"
    with pytest.raises(CircuitoAberto) as e:      # recusa sem chamar a funcao
        cb.chamar(lambda: pytest.fail("nao deveria chamar"))
    assert 0 < e.value.retry_apos <= 20
    rel.t += 20
    assert cb.chamar(lambda: "ok") == "ok"        # sonda com sucesso
    assert cb.estado == "fechado" and cb.falhas == 0


def test_falha_na_sonda_reabre():
    rel = Relogio()
    cb = CircuitBreaker(limite_falhas=1, espera_segundos=10, relogio=rel)
    with pytest.raises(ConnectionError):
        cb.chamar(falha)
    rel.t += 10
    with pytest.raises(ConnectionError):
        cb.chamar(falha)
    assert cb.estado == "aberto"
    assert cb.status()["reabre_em_segundos"] == 10


def test_em_meio_so_uma_chamada_de_teste_passa():
    rel = Relogio()
    cb = CircuitBreaker(limite_falhas=1, espera_segundos=5, relogio=rel)
    with pytest.raises(ConnectionError):
        cb.chamar(falha)
    rel.t += 5
    dentro, liberar = threading.Event(), threading.Event()
    resultado = []

    def sonda():
        dentro.set()
        liberar.wait(5)
        return "ok"

    t = threading.Thread(target=lambda: resultado.append(cb.chamar(sonda)))
    t.start()
    assert dentro.wait(5)
    assert cb.estado == "meio"
    with pytest.raises(CircuitoAberto):           # segunda chamada e recusada
        cb.chamar(lambda: "intruso")
    liberar.set()
    t.join()
    assert resultado == ["ok"] and cb.estado == "fechado"


def test_sucesso_zera_contagem():
    cb = CircuitBreaker(limite_falhas=3)
    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.chamar(falha)
    cb.chamar(lambda: 1)
    assert cb.falhas == 0 and cb.estado == "fechado"


def test_retry_backoff_exponencial_com_sleep_mockado():
    esperas, chamadas = [], []

    def instavel():
        chamadas.append(1)
        if len(chamadas) < 3:
            raise requests.Timeout("lento")
        return "ok"

    r = com_retentativas(instavel, tentativas=4, base=0.5, teto=5,
                         dormir=esperas.append, sorteio=lambda a, b: b)  # jitter = maximo
    assert r == "ok" and len(chamadas) == 3
    assert esperas == [0.5, 1.0]                  # 0.5 * 2^n


def test_retry_jitter_dentro_do_intervalo():
    esperas = []
    with pytest.raises(requests.ConnectionError):
        com_retentativas(lambda: (_ for _ in ()).throw(requests.ConnectionError()),
                         tentativas=4, base=1, teto=3, dormir=esperas.append)
    assert len(esperas) == 3
    assert all(0 <= e <= m for e, m in zip(esperas, [1, 2, 3]))


def _http_erro(status):
    resp = requests.Response()
    resp.status_code = status
    return requests.HTTPError(response=resp)


def test_so_erros_transitorios_sao_repetidos():
    assert e_transitorio(_http_erro(503)) and e_transitorio(_http_erro(429))
    assert not e_transitorio(_http_erro(401)) and not e_transitorio(ValueError())
    chamadas = []

    def nao_transitorio():
        chamadas.append(1)
        raise _http_erro(401)

    with pytest.raises(requests.HTTPError):
        com_retentativas(nao_transitorio, tentativas=3, dormir=lambda s: None)
    assert len(chamadas) == 1


# ---- endpoint /perguntar ---------------------------------------------------
@pytest.fixture
def cli(monkeypatch):
    ger.disjuntor = CircuitBreaker(limite_falhas=2, espera_segundos=20, relogio=Relogio())
    monkeypatch.setattr(ger, "LLM_TENTATIVAS", 1)
    return TestClient(ger.app)


def fingir_recuperacao(monkeypatch, resultados=None, erro=None, status=200):
    class R:
        status_code = status

        def json(self):
            return {"resultados": resultados}

    def post(*a, **k):
        if erro:
            raise erro
        return R()
    monkeypatch.setattr(ger.requests, "post", post)


def test_perguntar_devolve_resposta_contexto_e_fontes(monkeypatch, cli):
    fingir_recuperacao(monkeypatch, [{"texto": "t1", "origem": "a.txt", "score": .9},
                                     {"texto": "t2", "origem": "a.txt", "score": .5}])
    r = cli.post("/perguntar", json={"pergunta": "q"})
    assert r.status_code == 200
    j = r.json()
    assert j["contexto"] == ["t1", "t2"] and j["fontes"] == ["a.txt"]
    assert "resposta" in j and r.headers["X-Request-ID"]


def test_request_id_e_propagado(monkeypatch, cli):
    vistos = {}

    class R:
        status_code = 200

        def json(self):
            return {"resultados": []}

    def post(*a, **k):
        vistos.update(k["headers"])
        return R()
    monkeypatch.setattr(ger.requests, "post", post)
    r = cli.post("/perguntar", json={"pergunta": "q"}, headers={"X-Request-ID": "abc123"})
    assert vistos["X-Request-ID"] == "abc123" and r.headers["X-Request-ID"] == "abc123"


def test_circuito_aberto_vira_503_com_retry_after(monkeypatch, cli):
    fingir_recuperacao(monkeypatch, [{"texto": "t", "origem": "a", "score": 1}])
    monkeypatch.setenv("LLM_SIMULAR_FALHA", "1")
    for _ in range(2):
        assert cli.post("/perguntar", json={"pergunta": "q"}).status_code == 502
    r = cli.post("/perguntar", json={"pergunta": "q"})
    assert r.status_code == 503
    assert int(r.headers["Retry-After"]) >= 1
    assert "disjuntor" in r.json()["detail"]
    s = cli.get("/saude").json()["disjuntor"]
    assert s["estado"] == "aberto" and s["falhas"] == 2 and s["reabre_em_segundos"] > 0


def test_recuperacao_fora_do_ar_da_503_e_nao_500(monkeypatch, cli):
    fingir_recuperacao(monkeypatch, erro=requests.ConnectionError("down"))
    r = cli.post("/perguntar", json={"pergunta": "q"})
    assert r.status_code == 503 and "recuperacao" in r.json()["detail"]


def test_recuperacao_com_erro_interno_da_502(monkeypatch, cli):
    fingir_recuperacao(monkeypatch, status=500)
    assert cli.post("/perguntar", json={"pergunta": "q"}).status_code == 502

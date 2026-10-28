import pytest
import requests
from fastapi.testclient import TestClient

from servicos.recuperacao import app as mod

ITENS = [
    {"texto": "O teorema CAP trata de consistencia e disponibilidade em particoes", "origem": "cap.txt"},
    {"texto": "Raft elege um lider e replica o log entre os nos", "origem": "raft.txt"},
    {"texto": "Sistemas distribuidos tem varios computadores cooperando", "origem": "sd.txt"},
]


class Resp:
    def __init__(self, dados):
        self._d = dados

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


@pytest.fixture(autouse=True)
def limpa_cache():
    mod._cache.update(chave=None, vetorizador=None, itens=[], vetores=[])


@pytest.fixture
def cli():
    return TestClient(mod.app)


def fingir_indice(monkeypatch, itens, chamadas=None):
    def get(url, **kw):
        if chamadas is not None:
            chamadas.append(url)
        return Resp({"total": len(itens), "versao": str(len(itens)), "itens": itens})
    monkeypatch.setattr(mod.requests, "get", get)


def test_ordena_por_score_e_respeita_top_k(monkeypatch, cli):
    fingir_indice(monkeypatch, ITENS)
    r = cli.post("/buscar", json={"pergunta": "o que diz o teorema CAP?", "top_k": 2}).json()
    res = r["resultados"]
    assert res[0]["origem"] == "cap.txt"
    assert len(res) <= 2
    assert [x["score"] for x in res] == sorted((x["score"] for x in res), reverse=True)
    assert set(res[0]) == {"texto", "origem", "score"}


def test_indice_vazio_devolve_lista_vazia(monkeypatch, cli):
    fingir_indice(monkeypatch, [])
    assert cli.post("/buscar", json={"pergunta": "algo"}).json() == {"resultados": []}


def test_ingestao_fora_do_ar_da_503(monkeypatch, cli):
    def get(*a, **k):
        raise requests.ConnectionError("recusada")
    monkeypatch.setattr(mod.requests, "get", get)
    r = cli.post("/buscar", json={"pergunta": "x"})
    assert r.status_code == 503 and "ingestao" in r.json()["detail"]


def test_cache_invalidado_quando_total_muda(monkeypatch, cli):
    fingir_indice(monkeypatch, ITENS[:2])
    cli.post("/buscar", json={"pergunta": "raft lider"})
    chave1 = mod._cache["chave"]
    cli.post("/buscar", json={"pergunta": "raft lider"})
    assert mod._cache["chave"] == chave1
    fingir_indice(monkeypatch, ITENS)
    r = cli.post("/buscar", json={"pergunta": "computadores cooperando"}).json()
    assert mod._cache["chave"] != chave1
    assert r["resultados"][0]["origem"] == "sd.txt"


def test_sem_termos_em_comum_nao_devolve_lixo(monkeypatch, cli):
    fingir_indice(monkeypatch, ITENS)
    assert cli.post("/buscar", json={"pergunta": "receita culinaria bolo"}).json()["resultados"] == []


def test_fora_do_dominio_so_com_palavras_funcionais_nao_devolve_nada(monkeypatch, cli):
    fingir_indice(monkeypatch, ITENS)
    for pergunta in ("qual a receita de bolo de chocolate?", "quem ganhou a copa de 2002?", "a"):
        assert cli.post("/buscar", json={"pergunta": pergunta}).json()["resultados"] == []


def test_acentos_nao_atrapalham(monkeypatch, cli):
    fingir_indice(monkeypatch, ITENS)
    res = cli.post("/buscar", json={"pergunta": "como o Raft elege um líder?"}).json()["resultados"]
    assert res and res[0]["origem"] == "raft.txt"


def test_score_minimo_filtra_trechos_fracos(monkeypatch, cli):
    fingir_indice(monkeypatch, ITENS)
    monkeypatch.setattr(mod, "SCORE_MINIMO", 0.99)
    assert cli.post("/buscar", json={"pergunta": "teorema CAP"}).json()["resultados"] == []

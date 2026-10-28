import json
import threading
import time

import fakeredis
import pytest
from fastapi.testclient import TestClient

from servicos.ingestao import app as ing
from servicos.ingestao import fila, worker
from servicos.ingestao.indice import Indice


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def ind(tmp_path):
    return Indice(str(tmp_path / "i.json"))


def msg(r, grupo_pronto=True):
    fila.garantir_grupo(r)
    lidos = r.xreadgroup(fila.GRUPO, "c1", {fila.STREAM: ">"}, count=1)
    (_, [(msg_id, campos)]) = lidos[0]
    return msg_id, campos


def test_sucesso_persiste_e_da_ack(r, ind):
    lote = fila.publicar(r, [{"texto": "raft elege lider", "origem": "r"}])
    msg_id, campos = msg(r)
    assert worker.processar(r, ind, msg_id, campos) == "concluido"
    assert ind.total() == 1
    assert fila.status(r, lote)["estado"] == "concluido"
    assert r.xpending(fila.STREAM, fila.GRUPO)["pending"] == 0     # ack feito


def test_sem_ack_antes_de_persistir(r, ind, monkeypatch):
    fila.publicar(r, [{"texto": "x yy", "origem": "r"}])
    msg_id, campos = msg(r)

    def quebra(docs):
        assert r.xpending(fila.STREAM, fila.GRUPO)["pending"] == 1  # ainda sem ack
        raise OSError("disco cheio")
    monkeypatch.setattr(ind, "adicionar", quebra)
    worker.processar(r, ind, msg_id, campos, dormir=lambda s: None)


def test_falha_reenfileira_e_apos_n_tentativas_vai_para_dlq(r, ind, monkeypatch):
    monkeypatch.setattr(ind, "adicionar", lambda d: (_ for _ in ()).throw(OSError("falha")))
    lote = fila.publicar(r, [{"texto": "abc def", "origem": "r"}])
    for esperado in ("pendente", "pendente", "falhou"):
        msg_id, campos = msg(r)
        assert worker.processar(r, ind, msg_id, campos, dormir=lambda s: None) == "falhou"
        assert fila.status(r, lote)["estado"] == esperado
    assert r.xlen(fila.DLQ) == 1
    assert r.xrange(fila.DLQ)[0][1]["lote"] == lote
    assert r.xpending(fila.STREAM, fila.GRUPO)["pending"] == 0
    assert ind.total() == 0


def test_mensagem_malformada_vai_para_dlq(r, ind):
    fila.garantir_grupo(r)
    r.xadd(fila.STREAM, {"lote": "ruim", "docs": "{nao e json", "tentativas": 0})
    for _ in range(fila.MAX_TENTATIVAS):
        msg_id, campos = msg(r)
        worker.processar(r, ind, msg_id, campos, dormir=lambda s: None)
    assert r.xlen(fila.DLQ) == 1


def test_reprocessar_lote_e_idempotente(r, ind):
    docs = [{"texto": "mesmo texto aqui", "origem": "r"}]
    fila.publicar(r, docs)
    fila.publicar(r, docs)
    for _ in range(2):
        worker.processar(r, ind, *msg(r))
    assert ind.total() == 1


def test_loop_do_worker_consome_em_thread(r, ind):
    lote = fila.publicar(r, [{"texto": "consenso por maioria", "origem": "r"}])
    parar = threading.Event()
    t = threading.Thread(target=worker.executar, args=(r, ind, "w1", parar.is_set, 100))
    t.start()
    for _ in range(50):
        if fila.status(r, lote)["estado"] == "concluido":
            break
        time.sleep(0.1)
    parar.set()
    t.join(5)
    assert fila.status(r, lote)["estado"] == "concluido" and ind.total() == 1


# ---- API ------------------------------------------------------------------
@pytest.fixture
def cli(r, ind, monkeypatch):
    monkeypatch.setattr(ing, "indice", ind)
    monkeypatch.setattr(ing, "_redis", r)
    return TestClient(ing.app)


def test_indexar_responde_202_e_status(cli, r, ind):
    resp = cli.post("/indexar", json=[{"texto": "cap trata particoes", "origem": "c"}])
    assert resp.status_code == 202
    lote = resp.json()["lote"]
    assert cli.get(f"/indexar/{lote}").json()["estado"] == "pendente"
    worker.processar(r, ind, *msg(r))
    assert cli.get(f"/indexar/{lote}").json()["estado"] == "concluido"
    assert cli.get("/indice").json()["total"] == 1       # API enxerga o que o worker gravou
    assert cli.get("/indexar/inexistente").status_code == 404


def test_indexar_sincrono(cli):
    resp = cli.post("/indexar?sincrono=true", json=[{"texto": "um doc", "origem": "a"}])
    assert resp.status_code == 200 and resp.json() == {"indexados": 1, "novos": 1}


def test_redis_fora_do_ar_indexa_sincrono(cli, monkeypatch):
    import redis

    def quebra(*a, **k):
        raise redis.ConnectionError("down")
    monkeypatch.setattr(ing.fila, "publicar", quebra)
    resp = cli.post("/indexar", json=[{"texto": "x", "origem": "a"}])
    assert resp.status_code == 200 and resp.json()["novos"] == 1 and "aviso" in resp.json()
    assert cli.get("/indice").json()["total"] == 1
    assert cli.get("/saude").status_code == 200

"""
Worker de ingestao: consome fila:ingestao, gera os embeddings (reajusta o
TF-IDF) e persiste o indice.

Falhas: o lote e re-enfileirado com tentativas+1; ao atingir MAX_TENTATIVAS vai
para fila:ingestao:dlq. O XACK da mensagem original so acontece DEPOIS de o
indice ser persistido (ou de o lote ter sido re-enfileirado / enviado a DLQ),
entao nenhuma mensagem se perde se o worker morrer no meio.

Rodar: python -m servicos.ingestao.worker
"""
import json
import logging
import os
import socket
import time

import redis

from servicos.comum.logs import configurar_logs, request_id_var
from servicos.ingestao import fila
from servicos.ingestao.indice import Indice

log = configurar_logs("worker")
HEARTBEAT = os.getenv("WORKER_HEARTBEAT", "/tmp/worker.hb")
RECLAMAR_APOS_MS = int(os.getenv("FILA_RECLAMAR_APOS_MS", "30000"))


def _concluir(r, msg_id):
    """XACK e remove a entrada do stream (assim XLEN = trabalho ainda nao concluido)."""
    r.xack(fila.STREAM, fila.GRUPO, msg_id)
    r.xdel(fila.STREAM, msg_id)


def processar(r, indice, msg_id, campos, dormir=time.sleep):
    lote = campos.get("lote", "?")
    request_id_var.set(f"lote-{lote}")
    tentativas = int(campos.get("tentativas", 0))
    chave = fila._chave(lote)
    try:
        r.hset(chave, mapping={"estado": "processando"})
        docs = json.loads(campos["docs"])
        if not isinstance(docs, list) or not all(
                isinstance(d, dict) and isinstance(d.get("texto"), str) for d in docs):
            raise ValueError("lote invalido: esperado lista de {texto, origem}")
        resultado = indice.adicionar(docs)
    except Exception as e:
        tentativas += 1
        log.error("lote %s falhou (tentativa %d/%d): %s", lote, tentativas,
                  fila.MAX_TENTATIVAS, e)
        if tentativas >= fila.MAX_TENTATIVAS:
            r.xadd(fila.DLQ, {"lote": lote, "docs": campos.get("docs", ""),
                              "tentativas": tentativas, "erro": str(e)})
            r.hset(chave, mapping={"estado": "falhou", "tentativas": tentativas,
                                   "erro": str(e)})
            log.error("lote %s enviado para a DLQ", lote)
        else:
            dormir(min(2 ** tentativas, 10))  # backoff simples antes de reenfileirar
            r.xadd(fila.STREAM, {"lote": lote, "docs": campos.get("docs", ""),
                                 "tentativas": tentativas})
            r.hset(chave, mapping={"estado": "pendente", "tentativas": tentativas,
                                   "erro": str(e)})
        _concluir(r, msg_id)
        return "falhou"
    r.hset(chave, mapping={"estado": "concluido", "novos": resultado["novos"],
                           "total": resultado["total"]})
    _concluir(r, msg_id)  # ack somente apos persistir
    log.info("lote %s concluido: +%d novos (total=%d)", lote, resultado["novos"],
             resultado["total"])
    return "concluido"


def _batimento():
    try:
        with open(HEARTBEAT, "a"):
            os.utime(HEARTBEAT, None)
    except OSError:
        pass


def executar(r, indice, consumidor, parar=lambda: False, bloquear_ms=2000):
    fila.garantir_grupo(r)
    ciclo = 0
    # 1) reprocessa o que ficou entregue a este consumidor sem ack (queda anterior)
    lidos = r.xreadgroup(fila.GRUPO, consumidor, {fila.STREAM: "0"}, count=50)
    for _, msgs in lidos or []:
        for msg_id, campos in msgs:
            processar(r, indice, msg_id, campos)
    while not parar():
        _batimento()
        ciclo += 1
        if ciclo % 10 == 0:  # 2) assume mensagens de consumidores que morreram
            _, reclamadas, *_ = r.xautoclaim(fila.STREAM, fila.GRUPO, consumidor,
                                             min_idle_time=RECLAMAR_APOS_MS, count=10)
            for msg_id, campos in reclamadas:
                if campos:
                    processar(r, indice, msg_id, campos)
        lidos = r.xreadgroup(fila.GRUPO, consumidor, {fila.STREAM: ">"},
                             count=1, block=bloquear_ms)
        for _, msgs in lidos or []:
            for msg_id, campos in msgs:
                processar(r, indice, msg_id, campos)


def main():
    consumidor = f"{socket.gethostname()}-{os.getpid()}"
    indice = Indice(os.getenv("INDICE_PATH", "dados/indice.json"))
    log.info("worker %s iniciado", consumidor)
    while True:
        try:
            executar(fila.conectar(), indice, consumidor)
        except (redis.ConnectionError, redis.TimeoutError) as e:
            log.error("redis indisponivel (%s); tentando de novo em 2s", e)
            time.sleep(2)


if __name__ == "__main__":
    main()

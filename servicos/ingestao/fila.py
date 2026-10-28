"""
Fila de ingestao sobre Redis Streams (consumer group).

  fila:ingestao       lotes a indexar          (XADD pela API, XREADGROUP pelo worker)
  fila:ingestao:dlq   lotes que falharam N vezes (fila de mortos)
  ingestao:lote:<id>  hash com o status do lote (consultado em GET /indexar/<id>)

Garantia: entrega "ao menos uma vez". O worker so faz XACK depois de persistir o
indice; como a indexacao deduplica por hash, reprocessar um lote e inofensivo.
"""
import json
import os
import uuid

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
STREAM = "fila:ingestao"
DLQ = "fila:ingestao:dlq"
GRUPO = "grupo-ingestao"
MAX_TENTATIVAS = int(os.getenv("FILA_MAX_TENTATIVAS", "3"))
TTL_STATUS = 24 * 3600


def conectar(url=None):
    return redis.Redis.from_url(url or REDIS_URL, decode_responses=True,
                                socket_connect_timeout=3, socket_timeout=10)


def _chave(lote):
    return f"ingestao:lote:{lote}"


def garantir_grupo(r):
    try:
        r.xgroup_create(STREAM, GRUPO, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def publicar(r, docs):
    """Enfileira um lote e devolve o id do lote (status inicial: pendente)."""
    lote = uuid.uuid4().hex[:12]
    r.hset(_chave(lote), mapping={"estado": "pendente", "documentos": len(docs),
                                  "tentativas": 0})
    r.expire(_chave(lote), TTL_STATUS)
    r.xadd(STREAM, {"lote": lote, "docs": json.dumps(docs), "tentativas": 0})
    return lote


def status(r, lote):
    dados = r.hgetall(_chave(lote))
    return dados or None


def metricas(r):
    """Numeros para /saude: na fila (inclui em processamento), entregues sem ack e mortos (DLQ)."""
    na_fila = r.xlen(STREAM)
    sem_ack = 0
    try:
        sem_ack = r.xpending(STREAM, GRUPO)["pending"]
    except redis.ResponseError:  # grupo ainda nao existe
        pass
    return {"na_fila": na_fila, "sem_ack": sem_ack, "mortos": r.xlen(DLQ)}

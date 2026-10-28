"""
Servico 1 - INGESTAO: recebe documentos, gera embeddings e armazena.

POST /indexar responde 202 e publica o lote em fila:ingestao (Redis Streams);
o worker (servicos/ingestao/worker.py) consome, reajusta o TF-IDF e persiste o
indice em arquivo (INDICE_PATH). Use ?sincrono=true para indexar na hora; se o
Redis estiver fora do ar, /indexar cai para esse modo (200 + "aviso").
O indice e recarregado do arquivo ao iniciar e a cada mudanca feita pelo worker.

Rodar: uvicorn servicos.ingestao.app:app --port 8001
"""
import os

import redis
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from servicos.comum.logs import configurar_logs, instalar_request_id
from servicos.ingestao import fila
from servicos.ingestao.chunking import carregar_diretorio
from servicos.ingestao.indice import Indice

log = configurar_logs("ingestao")
app = FastAPI(title="Ingestao - C2.A2")
instalar_request_id(app)

DOCUMENTOS_DIR = os.getenv("DOCUMENTOS_DIR", "documentos")
indice = Indice(os.getenv("INDICE_PATH", "dados/indice.json"))
_redis = None


def get_redis():
    global _redis
    if _redis is None:
        _redis = fila.conectar()
    return _redis


class Documento(BaseModel):
    texto: str
    origem: str = "desconhecida"


def _enfileirar_ou_indexar(docs, sincrono):
    if sincrono:
        r = indice.adicionar(docs)
        return JSONResponse({"indexados": r["total"], "novos": r["novos"]})
    try:
        lote = fila.publicar(get_redis(), docs)
    except (redis.ConnectionError, redis.TimeoutError) as e:
        # degradacao: sem fila, indexa na hora (o indice deduplica, entao e seguro)
        log.warning("redis indisponivel (%s); indexando de forma sincrona", e)
        r = indice.adicionar(docs)
        return JSONResponse({"indexados": r["total"], "novos": r["novos"],
                             "aviso": "fila indisponivel (Redis); indexado de forma sincrona"})
    log.info("lote %s enfileirado (%d docs)", lote, len(docs))
    return JSONResponse(status_code=202, content={
        "lote": lote, "estado": "pendente", "documentos": len(docs),
        "status_url": f"/indexar/{lote}"})


@app.post("/indexar")
def indexar(docs: list[Documento], sincrono: bool = Query(False)):
    return _enfileirar_ou_indexar([d.model_dump() for d in docs], sincrono)


@app.get("/indexar/{lote}")
def status_lote(lote: str):
    try:
        st = fila.status(get_redis(), lote)
    except (redis.ConnectionError, redis.TimeoutError):
        raise HTTPException(503, "fila indisponivel (Redis)")
    if st is None:
        raise HTTPException(404, "lote desconhecido (ou expirado)")
    return {"lote": lote, **st}


@app.post("/indexar-arquivos")
def indexar_arquivos(sincrono: bool = Query(False)):
    """Indexa documentos/*.txt (um trecho por paragrafo, origem = nome do arquivo)."""
    docs = carregar_diretorio(DOCUMENTOS_DIR)
    if not docs:
        raise HTTPException(404, f"nenhum .txt em {DOCUMENTOS_DIR}")
    return _enfileirar_ou_indexar(docs, sincrono)


@app.get("/indice")
def get_indice(vetores: bool = Query(True)):
    """Consumido pelo servico de recuperacao (vetores=false devolve so os textos)."""
    itens = indice.itens()
    return {"total": len(itens), "versao": indice.versao(),
            "itens": [{"texto": i["texto"], "origem": i["origem"],
                       **({"vetor": i["vetor"]} if vetores else {})} for i in itens]}


@app.get("/saude")
def saude():
    corpo = {"status": "ok", "documentos": indice.total()}
    try:
        corpo["fila"] = fila.metricas(get_redis())
    except (redis.ConnectionError, redis.TimeoutError):
        corpo["fila"] = "indisponivel"
    return corpo

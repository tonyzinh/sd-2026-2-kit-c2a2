"""
Servico 2 - RECUPERACAO: dada uma pergunta, acha os trechos mais relevantes.

Decisao sobre o vocabulario TF-IDF: o vocabulario/IDF e aprendido sobre o
corpus. Em vez de acoplar a Recuperacao aos vetores da Ingestao (que mudam de
dimensao a cada ingestao), a Recuperacao busca apenas os TEXTOS em
/indice?vetores=false, reajusta um Vetorizador LOCAL e vetoriza pergunta e
itens com ele - mesmo vocabulario dos dois lados, sempre consistente. O
resultado fica em cache e e invalidado quando (total, versao) do indice muda.

Rodar: uvicorn servicos.recuperacao.app:app --port 8002
"""
import os
import threading

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from servicos.comum.embeddings import Vetorizador, similaridade
from servicos.comum.logs import cabecalhos_saida, configurar_logs, instalar_request_id

log = configurar_logs("recuperacao")
app = FastAPI(title="Recuperacao - C2.A2")
instalar_request_id(app)
URL_INGESTAO = os.getenv("URL_INGESTAO", "http://localhost:8001")

_lock = threading.Lock()
_cache = {"chave": None, "vetorizador": None, "itens": [], "vetores": []}


class Consulta(BaseModel):
    pergunta: str
    top_k: int = Field(3, ge=1, le=50)


def _obter_indice():
    try:
        r = requests.get(f"{URL_INGESTAO}/indice", params={"vetores": "false"},
                         headers=cabecalhos_saida(), timeout=10)
        r.raise_for_status()
    except (requests.ConnectionError, requests.Timeout) as e:
        log.error("ingestao indisponivel: %s", e)
        raise HTTPException(503, "servico de ingestao indisponivel; tente novamente")
    except requests.RequestException as e:
        log.error("erro na ingestao: %s", e)
        raise HTTPException(502, "erro ao consultar o indice na ingestao")
    return r.json()


def _preparar(dados):
    """Devolve (vetorizador, itens, vetores), reajustando se o indice mudou."""
    chave = (dados["total"], dados.get("versao"))
    with _lock:
        if _cache["chave"] != chave:
            itens = dados["itens"]
            vet = Vetorizador()
            try:
                vet.ajustar([i["texto"] for i in itens])
                vetores = [vet.vetorizar(i["texto"]) for i in itens]
            except ValueError:  # vocabulario vazio
                vet, vetores = None, []
            _cache.update(chave=chave, vetorizador=vet, itens=itens, vetores=vetores)
            log.info("cache de vetores reconstruido (%d itens)", len(itens))
        return _cache["vetorizador"], _cache["itens"], _cache["vetores"]


@app.post("/buscar")
def buscar(consulta: Consulta):
    """Devolve os top_k trechos mais parecidos com a pergunta (score > 0)."""
    dados = _obter_indice()
    if not dados["itens"]:
        return {"resultados": []}
    vet, itens, vetores = _preparar(dados)
    if vet is None:
        return {"resultados": []}
    q = vet.vetorizar(consulta.pergunta)
    pontuados = [(similaridade(q, v), i) for v, i in zip(vetores, itens)]
    pontuados = [p for p in pontuados if p[0] > 0]
    pontuados.sort(key=lambda p: p[0], reverse=True)
    resultados = [{"texto": i["texto"], "origem": i["origem"], "score": round(s, 4)}
                  for s, i in pontuados[:consulta.top_k]]
    log.info("busca top_k=%d -> %d resultados", consulta.top_k, len(resultados))
    return {"resultados": resultados}


@app.get("/saude")
def saude():
    return {"status": "ok", "itens_em_cache": len(_cache["itens"])}

"""
Servico 3 - GERACAO: monta o prompt com o contexto e chama o LLM.

A chamada ao LLM e protegida assim (de fora para dentro):
    disjuntor.chamar( com_retentativas( gerar ) )
Cada chamada protegida = 1 tentativa + retries (backoff exponencial com jitter,
so para erros transitorios, com timeout LLM_TIMEOUT). O disjuntor so conta UMA
falha quando os retries se esgotam; assim um solavanco isolado nao o abre, mas
um LLM fora do ar sim.

Rodar: uvicorn servicos.geracao.app:app --port 8003
"""
import math
import os

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from servicos.comum.circuit_breaker import CircuitBreaker, CircuitoAberto
from servicos.comum.llm import gerar
from servicos.comum.logs import cabecalhos_saida, configurar_logs, instalar_request_id
from servicos.comum.retry import com_retentativas

log = configurar_logs("geracao")
configurar_logs("disjuntor")  # transicoes de estado e retentativas saem com timestamp e request-id
configurar_logs("retry")
app = FastAPI(title="Geracao - C2.A2")
instalar_request_id(app)
URL_RECUPERACAO = os.getenv("URL_RECUPERACAO", "http://localhost:8002")
TOP_K = int(os.getenv("TOP_K", "3"))
LLM_TENTATIVAS = int(os.getenv("LLM_TENTATIVAS", "3"))

disjuntor = CircuitBreaker(
    limite_falhas=int(os.getenv("BREAKER_LIMITE_FALHAS", "3")),
    espera_segundos=float(os.getenv("BREAKER_ESPERA", "20")),
)


class Pergunta(BaseModel):
    pergunta: str


def _buscar_contexto(pergunta):
    try:
        r = requests.post(f"{URL_RECUPERACAO}/buscar",
                          json={"pergunta": pergunta, "top_k": TOP_K},
                          headers=cabecalhos_saida(), timeout=10)
    except (requests.ConnectionError, requests.Timeout) as e:
        log.error("recuperacao indisponivel: %s", e)
        raise HTTPException(503, "servico de recuperacao indisponivel; tente novamente")
    if r.status_code >= 400:
        log.error("recuperacao respondeu %s", r.status_code)
        codigo = 503 if r.status_code == 503 else 502
        raise HTTPException(codigo, f"falha no servico de recuperacao (HTTP {r.status_code})")
    return r.json()["resultados"]


@app.post("/perguntar")
def perguntar(p: Pergunta):
    log.info("pergunta recebida: %r", p.pergunta)
    resultados = _buscar_contexto(p.pergunta)
    contexto = [t["texto"] for t in resultados]
    fontes = list(dict.fromkeys(t["origem"] for t in resultados))

    if not contexto:
        return {"pergunta": p.pergunta,
                "resposta": "Nao encontrei documentos relevantes para responder.",
                "contexto": [], "fontes": []}

    try:
        resposta = disjuntor.chamar(com_retentativas, gerar, p.pergunta, contexto,
                                    tentativas=LLM_TENTATIVAS)
    except CircuitoAberto as e:
        espera = max(1, math.ceil(e.retry_apos))
        log.warning("circuito aberto, recusando (retry em %ss)", espera)
        return JSONResponse(
            status_code=503, headers={"Retry-After": str(espera)},
            content={"detail": "LLM temporariamente indisponivel (disjuntor aberto); "
                               f"tente novamente em {espera}s"})
    except Exception as e:
        log.error("falha ao chamar o LLM apos retentativas: %s", e)
        raise HTTPException(502, "falha ao chamar o LLM")

    return {"pergunta": p.pergunta, "resposta": resposta,
            "contexto": contexto, "fontes": fontes}


@app.get("/saude")
def saude():
    return {"status": "ok", "disjuntor": disjuntor.status()}

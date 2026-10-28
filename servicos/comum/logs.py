"""
Logs com X-Request-ID - compartilhado pelos servicos.

Cada requisicao recebe (ou herda do chamador) um X-Request-ID, guardado em um
ContextVar. O filtro de log o injeta em toda linha e cabecalhos_saida() o
repassa nas chamadas HTTP entre servicos, permitindo seguir uma pergunta
pelos tres logs.
"""
import logging
import os
import uuid
from contextvars import ContextVar

CABECALHO = "X-Request-ID"
request_id_var = ContextVar("request_id", default="-")


class _FiltroRequestId(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


def configurar_logs(servico):
    logger = logging.getLogger(servico)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] [rid=%(request_id)s] %(message)s"))
        handler.addFilter(_FiltroRequestId())
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(os.getenv("LOG_NIVEL", "INFO"))
    return logger


def cabecalhos_saida():
    """Cabecalhos a repassar em chamadas HTTP para outros servicos."""
    return {CABECALHO: request_id_var.get()}


def instalar_request_id(app):
    @app.middleware("http")
    async def _request_id(request, call_next):
        rid = request.headers.get(CABECALHO) or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        try:
            resposta = await call_next(request)
        finally:
            request_id_var.reset(token)
        resposta.headers[CABECALHO] = rid
        return resposta

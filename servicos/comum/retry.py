"""Retentativa com backoff exponencial + jitter, apenas para erros transitorios."""
import logging
import random
import time

import requests

log = logging.getLogger("retry")


def e_transitorio(exc):
    """timeout, ConnectionError, 429 e 5xx sao transitorios; 4xx (exceto 429) nao."""
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


def com_retentativas(funcao, *args, tentativas=3, base=0.5, teto=5.0,
                     dormir=time.sleep, sorteio=random.uniform, **kwargs):
    """Chama funcao; em erro transitorio espera sorteio(0, min(teto, base*2^n)) e repete
    (full jitter). Erros nao transitorios sobem na hora; apos esgotar, sobe o ultimo."""
    for n in range(tentativas):
        try:
            return funcao(*args, **kwargs)
        except Exception as exc:
            if n == tentativas - 1 or not e_transitorio(exc):
                raise
            espera = sorteio(0, min(teto, base * 2 ** n))
            log.warning("erro transitorio (%s); tentativa %d/%d, nova em %.2fs",
                        type(exc).__name__, n + 1, tentativas, espera)
            dormir(espera)

"""Carrega o .env (se existir) para que `cp .env.example .env` valha tambem fora do Docker.

Variaveis ja definidas no ambiente (ex.: pelo docker compose) tem prioridade.
"""
try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:  # python-dotenv opcional: sem ele, so o ambiente vale
    pass

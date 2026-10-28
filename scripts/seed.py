"""Carrega documentos/*.txt na ingestao (via fila) e espera o worker concluir.

Uso: python scripts/seed.py [URL_INGESTAO]
"""
import os
import sys
import time

import requests

url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("URL_INGESTAO", "http://localhost:8001")
r = requests.post(f"{url}/indexar-arquivos", timeout=30)
print(r.status_code, r.text)
if r.status_code == 202:
    lote = r.json()["lote"]
    for _ in range(60):
        st = requests.get(f"{url}/indexar/{lote}", timeout=10).json()
        if st["estado"] in ("concluido", "falhou"):
            print(st)
            sys.exit(0 if st["estado"] == "concluido" else 1)
        time.sleep(1)
    print("timeout esperando o worker")
    sys.exit(1)
sys.exit(0 if r.ok else 1)

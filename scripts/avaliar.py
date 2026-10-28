"""Avaliacao automatica simples da recuperacao: para cada pergunta, a fonte
esperada aparece no top-k? Uso: python scripts/avaliar.py [URL_RECUPERACAO]"""
import os
import sys

import requests

URL = sys.argv[1] if len(sys.argv) > 1 else os.getenv("URL_RECUPERACAO", "http://localhost:8002")
CASOS = [
    ("o que diz o teorema CAP?", "teorema_cap.txt"),
    ("escolha entre consistencia e disponibilidade na particao", "teorema_cap.txt"),
    ("como o Raft elege um lider?", "consenso_raft.txt"),
    ("o que e um sistema distribuido?", "sistemas_distribuidos.txt"),
]
acertos = 0
for pergunta, esperada in CASOS:
    res = requests.post(f"{URL}/buscar", json={"pergunta": pergunta, "top_k": 3}, timeout=10).json()["resultados"]
    top1 = res[0]["origem"] if res else None
    ok = top1 == esperada
    acertos += ok
    print(f"[{'OK' if ok else 'FALHA'}] {pergunta!r} -> {top1} (esperado {esperada})")
print(f"precisao@1 = {acertos}/{len(CASOS)}")
sys.exit(0 if acertos == len(CASOS) else 1)

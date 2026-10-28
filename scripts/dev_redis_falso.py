"""Servidor Redis falso (fakeredis) so para desenvolvimento SEM Redis/Docker.
Uso: python scripts/dev_redis_falso.py [porta]   (requer requirements-dev.txt)"""
import sys

from fakeredis import TcpFakeServer

porta = int(sys.argv[1]) if len(sys.argv) > 1 else 6379
servidor = TcpFakeServer(("127.0.0.1", porta), server_type="redis")
print(f"redis falso em {porta}", flush=True)
servidor.serve_forever()

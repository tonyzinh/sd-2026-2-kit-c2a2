#!/usr/bin/env bash
# Sobe tudo localmente SEM Docker (Redis falso + 3 servicos + worker). Logs em dados/logs.
# Uso: scripts/dev_local.sh   (Ctrl+C encerra tudo). Requer: pip install -r requirements-dev.txt
cd "$(dirname "$0")/.."
PY=${PY:-python}
[ -x .venv/Scripts/python ] && PY=.venv/Scripts/python
[ -x .venv/bin/python ] && PY=.venv/bin/python
mkdir -p dados/logs
export INDICE_PATH=${INDICE_PATH:-dados/indice.json} WORKER_HEARTBEAT=dados/hb
trap 'kill $(jobs -p) 2>/dev/null' EXIT
$PY scripts/dev_redis_falso.py 6379 >dados/logs/redis.log 2>&1 &
sleep 2
$PY -m uvicorn servicos.ingestao.app:app --port 8001 >dados/logs/ingestao.log 2>&1 &
$PY -m servicos.ingestao.worker >dados/logs/worker.log 2>&1 &
$PY -m uvicorn servicos.recuperacao.app:app --port 8002 >dados/logs/recuperacao.log 2>&1 &
$PY -m uvicorn servicos.geracao.app:app --port 8003 >dados/logs/geracao.log 2>&1 &
echo "servicos no ar (8001 ingestao, 8002 recuperacao, 8003 geracao). Ctrl+C para parar."
wait

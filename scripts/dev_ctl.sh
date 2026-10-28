#!/usr/bin/env bash
# Comandos auxiliares para o teste de falhas SEM Docker (usados com scripts/dev_local.sh).
# Uso: CMD_PARAR_REC="scripts/dev_ctl.sh parar-rec" ... scripts/teste_falhas.sh
cd "$(dirname "$0")/.."
PY=${PY:-python}
[ -x .venv/Scripts/python ] && PY=.venv/Scripts/python
[ -x .venv/bin/python ] && PY=.venv/bin/python
case "$1" in
  parar-rec)  powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8002 -State Listen | ForEach-Object { Stop-Process -Id \$_.OwningProcess -Force }" 2>/dev/null \
              || fuser -k 8002/tcp ;;
  iniciar-rec) INDICE_PATH=${INDICE_PATH:-dados/indice.json} nohup $PY -m uvicorn servicos.recuperacao.app:app --port 8002 >>dados/logs/recuperacao.log 2>&1 & ;;
  ligar-falha)    touch dados/llm_falha ;;
  desligar-falha) rm -f dados/llm_falha ;;
  xadd-invalido)  $PY -c "import redis;redis.Redis().xadd('fila:ingestao',{'lote':'lote-ruim','docs':'{nao-e-json','tentativas':0})" ;;
esac

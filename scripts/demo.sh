#!/usr/bin/env bash
# Demonstracao: sobe (opcional), indexa documentos/ via fila e faz uma pergunta.
# Uso: scripts/demo.sh                 -> docker compose up --build e roda a demo
#      SEM_SUBIR=1 scripts/demo.sh      -> so roda a demo (servicos ja no ar)
ING=${URL_INGESTAO:-http://localhost:8001}
GER=${URL_GERACAO:-http://localhost:8003}
PERGUNTA=${PERGUNTA:-o que diz o teorema CAP?}
cd "$(dirname "$0")/.."

if [ -z "$SEM_SUBIR" ]; then
  echo "== subindo com docker compose =="
  docker compose up -d --build --wait || exit 1
fi

echo "== saude =="
curl -s "$ING/saude"; echo
echo "== indexando documentos/ (assincrono, via fila Redis) =="
RESP=$(curl -s -XPOST "$ING/indexar-arquivos"); echo "$RESP"
LOTE=$(echo "$RESP" | sed -n 's/.*"lote":"\([^"]*\)".*/\1/p')
for _ in $(seq 1 30); do
  ST=$(curl -s "$ING/indexar/$LOTE")
  case "$ST" in *concluido*|*falhou*) break;; esac
  sleep 1
done
echo "status do lote: $ST"
echo "== pergunta: $PERGUNTA =="
curl -s -XPOST "$GER/perguntar" -H 'Content-Type: application/json' \
  -H 'X-Request-ID: demo-001' -d "{\"pergunta\":\"$PERGUNTA\"}"
echo

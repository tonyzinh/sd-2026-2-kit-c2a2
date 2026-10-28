#!/usr/bin/env bash
# Cenarios de falha ("Antes de entregar" do TAREFAS.md). Os servicos devem estar no ar.
# Por padrao usa docker compose; para rodar sem Docker, sobrescreva os CMD_* (veja README).
# Os CMD_* sao executados com eval.
GER=${URL_GERACAO:-http://localhost:8003}
CMD_PARAR_REC=${CMD_PARAR_REC:-docker compose stop recuperacao}
CMD_INICIAR_REC=${CMD_INICIAR_REC:-docker compose start recuperacao}
CMD_LIGAR_FALHA=${CMD_LIGAR_FALHA:-docker compose exec -T geracao touch /tmp/llm_falha}
CMD_DESLIGAR_FALHA=${CMD_DESLIGAR_FALHA:-docker compose exec -T geracao rm -f /tmp/llm_falha}
CMD_XADD_INVALIDO=${CMD_XADD_INVALIDO:-'docker compose exec -T redis redis-cli XADD fila:ingestao "*" lote lote-ruim docs "{nao-e-json" tentativas 0'}
ING=${URL_INGESTAO:-http://localhost:8001}

perguntar() {
  curl -s -i -m 120 -XPOST "$GER/perguntar" -H 'Content-Type: application/json' \
    -d '{"pergunta":"o que diz o teorema CAP?"}' | tr -d '\r' | cut -c1-230 \
    | grep -E '^(HTTP|retry-after|\{)'
}
saude() { echo -n "  /saude geracao: "; curl -s "$GER/saude"; echo; }

echo "### (a) LLM simulado: nenhuma chamada externa, o sistema segue de pe"
perguntar; saude

echo; echo "### (b) recuperacao fora do ar -> erro claro (503), nao 500"
eval "$CMD_PARAR_REC" >/dev/null 2>&1; sleep 2
perguntar
eval "$CMD_INICIAR_REC" >/dev/null 2>&1
for _ in $(seq 1 30); do curl -sf "${URL_RECUPERACAO:-http://localhost:8002}/saude" >/dev/null && break; sleep 1; done

echo; echo "### (c) LLM falhando: o circuito abre apos N falhas, passa por 'meio' e volta a 'fechado'"
LIM=$(curl -s "$GER/saude" | sed -n 's/.*"limite_falhas":\([0-9]*\).*/\1/p')
ESP=$(curl -s "$GER/saude" | sed -n 's/.*"espera_segundos":\([0-9.]*\).*/\1/p')
eval "$CMD_LIGAR_FALHA" >/dev/null 2>&1
for i in $(seq 1 "$LIM"); do echo "-- chamada $i (falha do LLM, retries esgotados):"; perguntar; done
saude
echo "-- chamada seguinte (circuito aberto, recusada na hora):"; perguntar
saude
eval "$CMD_DESLIGAR_FALHA" >/dev/null 2>&1
echo "-- aguardando ${ESP}s (espera do disjuntor)..."; sleep "$(awk "BEGIN{print int($ESP)+2}")"
echo "-- chamada de teste (estado 'meio' -> sucesso -> 'fechado'):"; perguntar
saude

echo; echo "### (d) mensagem invalida na fila -> reenfileirada e, apos 3 falhas, vai para a DLQ"
eval "$CMD_XADD_INVALIDO" >/dev/null 2>&1
for _ in $(seq 1 25); do
  S=$(curl -s "$ING/saude"); case "$S" in *'"mortos":0'*) sleep 1;; *) break;; esac
done
echo "  /saude ingestao: $S"

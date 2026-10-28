<div align="center">

# 🧠 Trabalho C2.A2 — RAG Distribuído

**Checklist de entrega · Ingestão • Recuperação • Geração**

![Núcleo](https://img.shields.io/badge/núcleo-6%2F6-success?style=for-the-badge)
![Extensões](https://img.shields.io/badge/extensões-2%2F4-yellow?style=for-the-badge)
![Pré-entrega](https://img.shields.io/badge/pré--entrega-3%2F3-success?style=for-the-badge)

</div>

---

## 📊 Progresso geral

```
Núcleo obrigatório   ██████████ 100%   (6/6)
Extensões opcionais  █████░░░░░  50%   (2/4)
Antes de entregar    ██████████ 100%   (3/3)
────────────────────────────────────────────
Total                ████████░░  85%   (11/13)
```

---

## 🎯 Núcleo obrigatório

| # | Status | Tarefa | Onde | O que fazer |
|:-:|:------:|--------|------|-------------|
| 1 | ✅ | **Persistir o índice** | `servicos/ingestao/app.py` | O índice some ao reiniciar. Guardar em arquivo ou banco vetorial. |
| 2 | ✅ | **Busca por similaridade** | `servicos/recuperacao/app.py` | Vetorizar a pergunta, comparar com cada documento e devolver os `top_k`. *(Aula 9/10)* |
| 3 | ✅ | **Circuit breaker no LLM** | `servicos/geracao/app.py` | Envolver `gerar(...)` com `disjuntor.chamar(...)` e devolver **503** com o circuito aberto. *(Aula 11)* |
| 4 | ✅ | **Mensageria** | novo *worker* + `docker-compose.yml` | Ao menos **uma** etapa do fluxo deve passar por fila, não por chamada direta. *(Aula 8)* |
| 5 | ✅ | **Fluxo completo** | ponta a ponta | Pergunta entra em `/perguntar` e sai uma resposta fundamentada nos documentos. |
| 6 | ✅ | **README com diagrama** | `README.md` | Diagrama da arquitetura dos três serviços. |

---

## 🚀 Extensões opcionais

- [ ] 🔀 **Reranking** — reordenar os trechos por relevância
- [x] 📚 **Citação de fontes** — indicar quais documentos embasaram a resposta
- [x] 🧪 **Avaliação automática** — verificação simples da qualidade da resposta
- [ ] 🧬 **Embeddings reais** — trocar TF-IDF por `sentence-transformers`

---

## 🔍 Antes de entregar

Testes de resiliência para confirmar que o sistema se comporta bem sob falhas.

- [x] 🌐 **Sem internet:** o modo simulado do LLM mantém o sistema de pé?
- [x] 🔌 **Recuperação fora do ar:** a Geração responde um **503** claro, sem quebrar?
- [x] ⚡ **LLM fora do ar:** o disjuntor abre?
- [x] 🔑 **Segredos:** a chave da API está **fora do código**, em variável de ambiente?

---

<div align="center">

<sub>✅ concluído &nbsp;·&nbsp; ⬜ pendente &nbsp;·&nbsp; Opcionais não bloqueiam a entrega</sub>

</div>
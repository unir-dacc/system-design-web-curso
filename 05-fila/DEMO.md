# Aula 05: Fila virtual

> **Objetivo:** em vez de barrar quem passa do limite, colocar todo mundo numa
> sala de espera e liberar as pessoas na ordem de chegada, conforme abrem vagas
> para comprar.

```
 usuário ──▶ POST /fila ───────────────▶ "sua senha é 1.214, posição 320"
             GET /fila/1214 (de tempos em tempos) ──▶ ... "liberado!"
                                                          │
      o liberador mantém no máximo N pessoas comprando ─┘  (contadores no Redis)
                                                          ▼
             mapa de assentos ──▶ compra (só com senha liberada: header X-Senha-Fila)
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`05-fila/`).

```bash
(cd ../04-nginx && docker compose down -v)   # derruba a etapa anterior
docker compose down -v
docker compose up -d --build --wait
```

Deixe à mão o relatório da aula 04 (`../04-nginx/relatorios/estreia.html`) para comparar.

---

## 1. O que a aula 04 deixou no ar

Volte ao relatório da 04: quantos usuários comuns foram barrados na porta? E os engajados, que tentam de novo sem parar?

Pergunta para a turma: *"quem chegou primeiro teve alguma vantagem? E o que um barrado faz em seguida?"*

## 2. O que mudou no código

```bash
git diff --no-index ../04-nginx/app app
```

| Arquivo | O que mostrar |
|---------|---------------|
| `app/fila.py` | Dois contadores no Redis (senhas emitidas e última liberada). A posição é uma subtração |
| `app/fila.py` | O liberador: um script que roda dentro do Redis e libera senhas sempre que abre uma vaga para comprar |
| `app/fila.py` | O "sinal de vida": cada consulta e cada tentativa de compra avisam que a pessoa ainda está lá. Quem some é pulado ou devolve a vaga |
| `app/routes/pedidos.py` | Sem senha liberada, a compra recebe 403. Uma senha vale uma compra |
| `app/main.py` | O liberador roda em segundo plano enquanto a aplicação está de pé |

Pergunta: *"por que a fila não guarda uma lista com todas as pessoas esperando?"*

## 3. A fila funcionando

```bash
# sem senha: a compra é recusada
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/pedidos -H 'Content-Type: application/json' -d '{}'

# 40 pessoas entram na fila de uma vez, e depois você
for i in $(seq 40); do curl -s -o /dev/null -X POST localhost:8000/fila & done; wait
curl -s -X POST localhost:8000/fila; echo
```

Use a sua senha para acompanhar a posição até ser liberado:

```bash
curl -s localhost:8000/fila/41; echo      # troque 41 pela sua senha
curl -s localhost:8000/fila; echo         # o estado da fila
```

👉 **Observe:** a posição caindo, o `consultar_em_s` e, no estado da fila, o `comprando_agora`.

Pergunta: *"por que o servidor diz de quanto em quanto tempo consultar?"*

## 4. A estreia

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

Abra o relatório desta aula ao lado do relatório da aula 04.

| Bloco | Perguntas |
|-------|-----------|
| A subida | Apareceu uma coluna nova. Em qual degrau a espera na fila passa da meta? |
| O pico: o caminho do usuário | Alguém foi barrado? Quantos saíram da fila? Quantos ainda estavam esperando quando o teste acabou? |
| O pico: a espera | Quem saiu da fila foi bem atendido? Quanto tempo esperou na fila antes? |
| Metas | Compare com a aula 04 |

Pergunta: *"é melhor esperar alguns minutos numa fila ou levar um 'tente de novo'?"*

Experimente outros limites de pessoas comprando ao mesmo tempo e rode a estreia de novo:

```bash
MAX_COMPRANDO=8 docker compose up -d ingressa
MAX_COMPRANDO=60 docker compose up -d ingressa
MAX_COMPRANDO=24 docker compose up -d ingressa      # volta ao padrão
```

Pergunta: *"qual é o número certo? O que acontece com o sistema do cinema se deixarmos gente demais comprando ao mesmo tempo?"*

Pergunta: *"por que limitar quantas pessoas estão comprando, e não quantas entram por segundo?"*

---

## Para fechar a aula

- A fila resolveu o problema de quem chegou primeiro?
- Ela deixou o sistema vender mais rápido?
- Quem ainda limita as vendas?

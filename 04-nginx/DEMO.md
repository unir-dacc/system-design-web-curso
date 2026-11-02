# Aula 04: Nginx + rate limit

> **Objetivo:** colocar uma porta de entrada na frente do Ingressa que recusa o
> excesso em vez de deixar tudo entrar, sem mudar uma linha do código do Ingressa.

```
                         ┌───────────────────────────┐
 usuários ─────────────▶ │  Nginx (a porta)          │── até X compras/s ──▶ Ingressa ──▶ cinema, gateway...
                         │  0.5 CPU / 64 MB          │
                         └─────────────┬─────────────┘
                                       └── o excesso: 429 "muita gente comprando agora, tente de novo"
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`04-nginx/`).

```bash
(cd ../03-async && docker compose down -v)   # derruba a etapa anterior
docker compose down -v
docker compose up -d --build --wait
```

Deixe à mão o relatório da aula 03 (`../03-async/relatorios/estreia.html`) para comparar.

---

## 1. O que a aula 03 deixou no ar

Na aula 03, o Ingressa async aceitava todo mundo que chegava e esbarrou num limite novo nos logs.

Pergunta para a turma: *"se o cinema só atende um número fixo de compras por vez, de que adianta deixar entrar mais gente do que isso?"*

## 2. O que mudou

```bash
git diff --no-index ../03-async/app app        # o código do Ingressa
git diff --no-index ../03-async/docker-compose.yml docker-compose.yml
```

| Arquivo | O que mostrar |
|---------|---------------|
| `nginx/templates/ingressa.conf.template` | `limit_req_zone` e `limit_req`: quantas compras (e mapas) por segundo passam pela porta. O excesso recebe 429 |
| `nginx/nginx.conf` | Um processo só, milhares de conexões: a mesma ideia do async, escrita em C |
| `docker-compose.yml` | O Nginx agora atende na porta 8000, e o Ingressa não tem mais porta publicada |

Pergunta: *"o código do Ingressa mudou? Por que isso é uma vantagem?"*

## 3. A porta funcionando

Dispare 30 compras ao mesmo tempo (os dados são inválidos de propósito, só para ver quem passa pela porta):

```bash
for i in $(seq 30); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/pedidos \
    -H 'Content-Type: application/json' -d '{}' &
done | sort | uniq -c
```

👉 **Observe:** quantas respostas são 422 (passaram pela porta e o Ingressa recusou os dados) e quantas são 429 (barradas na porta).

```bash
docker compose logs nginx | grep -c "limiting requests"
```

## 4. A estreia

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

Abra o relatório desta aula ao lado do relatório da aula 03.

| Bloco | Perguntas |
|-------|-----------|
| A subida | O que acontece acima do limite: o site fica lento ou barra gente? Olhe as colunas de tempo e a de barrados |
| O pico: o caminho do usuário | Quantos foram barrados na porta? E os que passaram, foram bem atendidos? |
| O pico: os engajados e o sistema | O que um usuário barrado faz? Quantos "barrados por segundo" o Nginx recusou? |

Pergunta: *"é justo? Quem chegou primeiro tem alguma vantagem sobre quem chegou depois?"*

Experimente outros limites e rode a estreia de novo:

```bash
LIMITE_COMPRAS_POR_S=4 docker compose up -d nginx
LIMITE_COMPRAS_POR_S=20 docker compose up -d nginx
LIMITE_COMPRAS_POR_S=8 docker compose up -d nginx      # volta ao padrão
```

## 5. Quem trabalhou no pico

Depois da estreia, pergunte ao cinema quantas vezes ele foi chamado e ao Redis quantas vezes o mapa não estava guardado:

```bash
curl -s localhost:8002/admin/estado | grep -o '"fila":{[^}]*}'
docker compose exec redis redis-cli INFO stats | grep keyspace
```

Pergunta: *"o mapa de cada sessão fica guardado por 5 segundos. Quantas vezes o cinema deveria ter sido chamado para mostrar mapas? Quantas vezes foi?"*

Pergunta: *"o que acontece no instante em que a cópia do mapa de uma sessão vence e 100 pessoas pedem esse mapa ao mesmo tempo?"* (dica: `app/cache.py`)

---

## Para fechar a aula

- O site caiu desta vez?
- Barrar o excesso na porta é justo com quem chegou primeiro?
- O que o usuário barrado faz em seguida, e o que isso causa?
- Qual é o próximo problema a resolver?

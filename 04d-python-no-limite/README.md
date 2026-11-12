# Aula 04d: Python no limite

> **Objetivo:** responder com medição a pergunta *"não dá para otimizar o
> Python até alcançar o Go?"*. A arquitetura e o hardware são os da etapa 04,
> os mesmos da 04c em Go. Muda o código: tudo o que deixa o Python mais rápido
> sem mudar a arquitetura.

```
                                        ┌──────────────────────────────┐
            ┌──────────────┐        ┌──▶│ Python no limite (backend 1) │──┐
 usuário ──▶│    Nginx     │────────┤   │ Granian, uvloop, msgspec,    │  ├──▶ Postgres, Redis,
            │ rate limit   │        │   │ asyncpg, mypyc               │  │    cinema, gateway
            └──────────────┘        │   └──────────────────────────────┘  │
                                    └──▶│ Python no limite (backend 2) │──┘
                                        └──────────────────────────────┘
```

O hardware, a divisão e os limites do Nginx são os mesmos da 04c.

**[🖊️ Abrir o diagrama desta etapa no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/04d-python-no-limite/arquitetura.excalidraw)**,
para desenhar por cima durante a aula. A peça nova da etapa está em amarelo.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`04d-python-no-limite/`).

```bash
docker compose -f ../04c-em-go/docker-compose.yml down -v   # as etapas usam os mesmos nomes
docker compose up -d --build --wait
```

Rode a estreia das etapas 04 e 04c antes da aula: o relatório desta etapa compara com o último resultado delas.

---

## 1. O que custa CPU no Python

Pergunta para a turma: *"numa requisição que só devolve uma resposta pronta do cache, onde o Python
gasta CPU?"* Liste no quadro as camadas por onde ela passa, da rede até a resposta.

## 2. O que mudou

Cada linha troca uma camada por uma versão mais rápida. Para cada uma, pergunte: *"essa camada
roda em Python ou em C/Rust agora?"*

| Camada | Antes (etapa 04b) | Aqui | Onde ver |
|--------|-------------------|------|----------|
| Python | 3.12 | 3.14 | `Dockerfile` |
| Servidor HTTP | uvicorn (HTTP lido em Python puro) | Granian (Rust) | `Dockerfile`, `app/main.py` |
| Laço de eventos | asyncio padrão | uvloop (C) | `Dockerfile` |
| Framework | FastAPI | nenhum: um roteador pequeno | `app/rotas.py` |
| JSON e validação | Pydantic | msgspec (C) | `app/modelos.py` |
| Banco | SQLAlchemy (ORM) + psycopg | SQL à mão + asyncpg | `app/banco.py`, `app/compra.py` |
| HTTP para o cinema e o gateway | httpx | aiohttp | `app/clientes.py` |
| Redis | redis-py | redis-py com hiredis (C) | `requirements.txt` |
| O código do app | interpretado | compilado para C com o mypyc | `Dockerfile` |

O QR code e o e-mail continuam: o trabalho do app é o mesmo.

Pergunta: *"o que o time perdeu com essas trocas? O que ficou mais difícil de manter?"*

## 3. A estreia

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | Compare com a 04b (o mesmo Python, sem as otimizações) e com a 04c (Go). Quanto da distância para o Go foi fechada? |
| A progressão | Em qual degrau os compradores deixam de comprar? E na 04c? |
| A velocidade de cada endpoint | As páginas ficaram tão rápidas quanto no Go? E a compra? |

👉 **Observe também:** no `docker compose stats`, a CPU dos backends. Compare com a da 04c no mesmo pico.

## Onde o banco gastou o tempo

Suba o painel do banco, o pgHero, e abra http://localhost:8080:

```bash
docker compose --profile observar up -d pghero
```

Depois de um teste, a aba **Queries** lista as consultas da rodada pelo tempo total que elas
tomaram do banco (as estatísticas são zeradas no começo de cada teste). O mesmo, no terminal:

```bash
docker compose exec postgres psql -U ingressa -c "SELECT calls AS vezes, round(mean_exec_time::numeric, 1) AS media_ms,
  round((100 * total_exec_time / sum(total_exec_time) OVER ())::numeric, 1) AS pct_do_tempo, left(query, 60) AS consulta
  FROM pg_stat_statements WHERE query NOT ILIKE '%pg_stat%' ORDER BY total_exec_time DESC LIMIT 5"
```

Pergunta: *"as consultas mudaram em relação à 04b? O que o ORM fazia de diferente?"*

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- Valeu a pena? O que custou cada otimização em código e em manutenção?
- Quando faz sentido otimizar a linguagem, e quando é melhor mudar a arquitetura?
- E se a 06 inteira fosse escrita assim?

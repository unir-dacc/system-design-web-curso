# Aula 04b: Async, esperar sem prender uma thread

> **Objetivo:** com o gateway de pagamento lento, cada compra passa segundos
> esperando com a requisição aberta. Mostrar o que muda quando o Ingressa espera
> sem prender uma thread (async), com a mesma arquitetura, o mesmo hardware e o
> mesmo teste da etapa 04. E discutir quando o async ajuda, e quando não.

```
                                        ┌──────────────────────────────┐
            ┌──────────────┐        ┌──▶│ Ingressa async (backend 1)   │──┐
 usuário ──▶│    Nginx     │────────┤   │ uma compra esperando o       │  ├──▶ Postgres, Redis,
            │ rate limit   │        │   │ gateway não ocupa uma thread │  │    cinema, gateway
            └──────────────┘        │   └──────────────────────────────┘  │
                                    └──▶│ Ingressa async (backend 2)   │──┘
                                        └──────────────────────────────┘
```

O hardware e a divisão são os mesmos da etapa 04. Muda o código do Ingressa e o limite das compras no Nginx.

**[🖊️ Abrir o diagrama desta etapa no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/04b-async/arquitetura.excalidraw)**,
para desenhar por cima durante a aula. A peça nova da etapa está em amarelo.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`04b-async/`).

```bash
docker compose -f ../04-rate-limit/docker-compose.yml down -v     # as etapas usam os mesmos nomes
docker compose up -d --build --wait
```

Rode o teste da etapa 04 antes da aula: o relatório desta etapa compara com o último resultado dela.

---

## 1. Onde a 04 parou

Abra `../04-rate-limit/relatorios/estreia.html`.

Pergunta para a turma: *"cada compra fica segundos esperando o gateway. O que o backend está fazendo
enquanto espera? Quantas compras cabem esperando ao mesmo tempo?"*

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `app/routes/` | As rotas são `async def`. Onde estão os `await`? |
| `app/clients.py` | O cinema e o gateway com `httpx.AsyncClient` |
| `app/db.py` | O banco assíncrono, com o mesmo driver. E o `awaitable_attrs`: no async, o ORM não busca uma relação sozinho |
| `app/notificacoes.py` | O QR code e o e-mail numa thread (`asyncio.to_thread`). Por quê? |
| `docker-compose.yml` | O limite de compras em andamento no Nginx: por que ele pode ser maior agora? |

Pergunta: *"o async faz o Python usar mais de um núcleo de CPU?"*

## 3. Threads contra async

Na 04, cada backend tem 40 threads. Faça a conta com a turma, pela Lei de Little:
**threads ocupadas = compras por segundo × tempo que cada compra espera.**

Pergunta: *"com o gateway levando alguns segundos por cobrança, quantas compras por segundo cabem
nas threads dos dois backends? E no async, o que passa a ser o limite?"*

## 4. A estreia

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 04? Nenhuma peça nova, nenhum hardware novo: de onde veio a diferença? |
| A progressão | Em qual degrau os compradores deixam de comprar? |
| A velocidade de cada endpoint | A compra ficou mais rápida? E as páginas? |

👉 **Observe também:** no `docker compose stats`, a CPU dos backends. Ela chegou no limite agora?

Experimente o gateway mais rápido e rode de novo:

```bash
curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"latencia_ms": 1000}'
```

Pergunta: *"com o gateway rápido, o async ainda faz diferença? Por quê?"*

Volte ao normal depois: `{"latencia_ms": 3000}`.

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

Pergunta: *"qual consulta tomou mais tempo do banco? Ela é lenta, ou roda muitas vezes?"*

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- Quando o async ajuda? E quando ele não muda nada?
- O usuário continua esperando o gateway com a tela aberta. E se ele não precisasse esperar?
- Se o gateway cair, o que acontece com as compras que estão esperando?

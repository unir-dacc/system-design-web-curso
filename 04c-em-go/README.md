# Aula 04c: A 04 em Go, a linguagem contra a arquitetura

> **Objetivo:** responder com medição a pergunta *"e se, em vez de fila e sala
> de espera, eu reescrevesse tudo numa linguagem mais rápida?"*. A arquitetura
> e o hardware são os da etapa 04 (Nginx com rate limit, 2 backends, cache, a
> compra inteira dentro da requisição). Só a linguagem muda: o Ingressa é o
> código Go da etapa 08, sem a fila e sem a sala de espera.

```
                                        ┌──────────────────────────────┐
            ┌──────────────┐        ┌──▶│ Ingressa em Go (backend 1)   │──┐
 usuário ──▶│    Nginx     │────────┤   │ a compra inteira dentro da   │  ├──▶ Postgres, Redis,
            │ rate limit   │        │   │ requisição, sem fila         │  │    cinema, gateway
            └──────────────┘        │   └──────────────────────────────┘  │
                                    └──▶│ Ingressa em Go (backend 2)   │──┘
                                        └──────────────────────────────┘
```

O hardware e a divisão são os mesmos da etapa 04 (2 CPUs e 2 GB). O limite das compras no Nginx é o da 04b: em Go, uma compra esperando o gateway não prende uma thread.

**[🖊️ Abrir o diagrama desta etapa no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/04c-em-go/arquitetura.excalidraw)**,
para desenhar por cima durante a aula. A peça nova da etapa está em amarelo.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`04c-em-go/`).

```bash
docker compose -f ../06-sala-de-espera/docker-compose.yml down -v   # as etapas usam os mesmos nomes
docker compose up -d --build --wait
```

Rode a estreia das etapas 04 e 06 antes da aula: o relatório desta etapa compara com o último resultado da 04, e a 06 fica aberta ao lado.

---

## 1. A aposta

Abra `../04-rate-limit/relatorios/estreia.html` e `../06-sala-de-espera/relatorios/estreia.html`.

Pergunta para a turma: *"da 04 para a 06 entraram a fila, o worker e a sala de espera. Se a gente
pulasse tudo isso e só reescrevesse a 04 em Go, chegaria no resultado da 06?"* Anote no quadro os palpites.

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `compra.go` | A compra inteira dentro da requisição, como na 04: cobra, confirma, emite e manda o e-mail |
| `rotas.go` | As mesmas rotas e respostas da 04. Compare com `../08-go/rotas.go`: o que sumiu? |
| `docker-compose.yml` | O hardware é o da 04. O limite das compras no Nginx: por que é o da 04b, e não o da 04? |

Pergunta: *"o que a linguagem consegue mudar numa compra que passa segundos esperando o gateway?"*

## 3. A estreia

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | Compare com a 04: o que o Go melhorou? E com a 06: quem ganhou, a linguagem ou a arquitetura? |
| A progressão | Em qual degrau os compradores deixam de comprar? É o mesmo da 04? Por quê? |
| A espera | Quanto tempo leva uma compra aqui? E na 06? O Go conseguiu encurtar esse tempo? |
| A velocidade de cada endpoint | As páginas ficaram mais rápidas? E a compra? |

👉 **Observe também:** no `docker compose stats`, a CPU dos backends. Ela chegou no limite? Se não foi a CPU, o que segurou as compras?

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

Pergunta: *"com o backend mais rápido, quem passou a ser o gargalo?"*

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- Quando trocar de linguagem resolve? E quando o problema é a arquitetura?
- O que a fila e a sala de espera fazem que nenhuma linguagem faz?
- E se a 06 inteira fosse reescrita em Go? (A etapa 08 responde, com mais hardware.)

# Mural · Aula 01: O ponto de partida

> **Objetivo:** apresentar o Mural funcionando. O lado do app é robusto e tem
> CPU de sobra; o banco foi escrito do jeito mais direto com o ORM e tem um
> orçamento pequeno e fixo. Colocá-lo à prova no dia em que um post viraliza.

```
                         ┌─────────────────────────────┐
                    ┌───▶│ Mural · réplica 1 (4 proc.) │───┐
            ┌─────┐ │    ├─────────────────────────────┤   │    ┌───────────────────────┐
 usuário ──▶│nginx│─┼───▶│ Mural · réplica 2 (4 proc.) │───┼──▶ │ Postgres              │
            └─────┘ │    ├─────────────────────────────┤   │    │ 100 mil usuários      │
                    ├───▶│ Mural · réplica 3 (4 proc.) │───┤    │ 1 milhão de posts     │
                    │    ├─────────────────────────────┤   │    │ 1 CPU / 1 GB          │
                    └───▶│ Mural · réplica 4 (4 proc.) │───┘    └───────────────────────┘
                         └─────────────────────────────┘
                          FastAPI async + ORM, CPU sem limite
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`mural/01-ponto-de-partida/`).

```bash
docker compose down -v          # garante que começa do zero
docker compose up -d --build --wait
```

A primeira subida cria a rede inteira (usuários, seguidores, posts, curtidas e comentários).
Deixe abertas duas abas: http://localhost:8000/docs e um terminal com `docker compose stats`.
Rode o teste uma vez antes da aula: logo depois da subida, o banco ainda não tem nada na memória.

---

## 1. Tour pelo código

| Arquivo | O que mostrar |
|---------|---------------|
| `docker-compose.yml` | O nginx, as 4 réplicas do app sem limite de CPU, e o Postgres com 1 CPU / 1 GB. Por que só o banco tem limite? |
| `nginx/nginx.conf` | Como o nginx distribui as requisições entre as réplicas |
| `app/db.py` | O pool de conexões de cada processo, e os dois limites de tempo. Quantas conexões chegam ao banco no total? |
| `app/main.py` | Quando o banco não dá conta a tempo, o Mural responde 503 na hora |
| `app/modelos.py` | As cinco tabelas e as relações entre elas. Quais colunas têm índice? |
| `app/banco.py` | Como a rede inicial é gerada: por que ela é desigual de propósito? |
| `app/routes/feed.py` | O feed: os posts de quem eu sigo, dos mais novos para os mais antigos, de 20 em 20 |
| `app/routes/esquemas.py` | `post_out`: como cada post do feed ganha o autor e o total de curtidas |
| `app/routes/posts.py` | Publicar, ver um post com os comentários, curtir, comentar |

Pergunta para a turma: *"para montar uma página do feed, quantas consultas vocês acham que o Mural faz no banco?"*

## 2. O Mural funcionando

```bash
curl -s "localhost:8000/feed?usuario_id=42" | head -c 600; echo
curl -s localhost:8000/usuarios/1 | head -c 300; echo
curl -s -X POST localhost:8000/posts -H 'Content-Type: application/json' -d '{"usuario_id": 42, "texto": "Meu primeiro post!"}'; echo
curl -s -X POST localhost:8000/posts/<id do post>/curtidas -H 'Content-Type: application/json' -d '{"usuario_id": 7}'; echo
```

👉 **Observe:** quem é o usuário 1, e o tempo de resposta do feed com `curl -s -o /dev/null -w "%{time_total}s\n" ...`.

## 3. Olhando o banco por dentro

```bash
docker compose exec postgres psql -U mural -c "SELECT seguido_id, count(*) FROM seguidores GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
docker compose exec postgres psql -U mural -c "\dt+"
docker compose exec postgres psql -U mural -c "\di"
```

A consulta do feed, como o ORM monta:

```bash
docker compose exec postgres psql -U mural -c "EXPLAIN ANALYZE
  SELECT * FROM posts WHERE autor_id IN (SELECT seguido_id FROM seguidores WHERE seguidor_id = 42)
  ORDER BY criado_em DESC LIMIT 20"
```

👉 **Observe:** quantos seguidores têm os usuários do topo, os índices que existem, e o plano da consulta do feed.

Para ver todas as consultas que uma página do feed faz, ligue o log do Postgres, abra um feed e desligue:

```bash
docker compose exec postgres psql -U mural -c "ALTER SYSTEM SET log_statement = 'all'" -c "SELECT pg_reload_conf()"
curl -s -o /dev/null "localhost:8000/feed?usuario_id=42"
docker compose exec postgres psql -U mural -c "ALTER SYSTEM RESET log_statement" -c "SELECT pg_reload_conf()"
docker compose logs postgres --since 1m | grep -c "LOG:  execute"
```

Pergunta: *"uma ForeignKey cria índice?"*

## 4. O dia em que um post viralizou

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/viral.js
xdg-open relatorios/viral.html
```

| Bloco | Perguntas |
|-------|-----------|
| Topo | Quantas requisições por segundo o Mural aguenta? E no pico, quantas foram atendidas? |
| A progressão | Em qual degrau as atendidas param de acompanhar as que chegam? |
| A velocidade de cada endpoint | Qual endpoint é o mais lento? Qual é o mais rápido? Por quê? |
| As curtidas | As curtidas gravadas no banco para o post viral e as que o Mural mostra batem? |

👉 **Observe também:** no `docker compose stats`, a CPU das réplicas do app e a do Postgres. Quem chega no limite? Quanto as réplicas estão usando da CPU que têm?

Pergunta: *"depois que o pico passa, o Mural volta a responder? O que impede que ele fique travado?"*

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- Onde o Mural passou o tempo? Adiantaria colocar mais réplicas do app?
- Quantas consultas custa uma página do feed? E a página 50?
- O que acontece com o feed quando a tabela de posts dobrar de tamanho?

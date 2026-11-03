# Mural · Aula 02: Índices

> **Objetivo:** dar ao banco os índices que as consultas do Mural precisam,
> sem mudar nenhuma consulta e com o mesmo Postgres, e medir quanto eles valem.

```
            ┌─────┐    ┌─────────────────────────────┐    ┌───────────────────────────────┐
 usuário ──▶│nginx│───▶│ Mural · 4 réplicas          │───▶│ Postgres                      │
            └─────┘    │ FastAPI async + ORM         │    │ + posts (autor_id, criado_em) │
                       │ CPU sem limite              │    │ + comentarios (post_id, ...)  │
                       └─────────────────────────────┘    │ 1 CPU / 1 GB                  │
                                                          └───────────────────────────────┘
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`mural/02-indices/`).

```bash
docker compose -f ../01-ponto-de-partida/docker-compose.yml down -v     # as etapas usam os mesmos nomes
docker compose up -d --build --wait
```

Rode o teste da etapa 01 antes da aula: o relatório desta etapa compara com o último resultado dela.
Rode também o teste desta etapa uma vez: logo depois da subida, o banco ainda não tem nada na memória.

---

## 1. O que a 01 mostrou

Abra `../01-ponto-de-partida/relatorios/viral.html`.

Pergunta para a turma: *"o app tinha CPU de sobra e o banco ficou no limite. O que o banco estava fazendo?"*

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `app/modelos.py` | Os dois índices compostos. Por que `(autor_id, criado_em)` e não só `autor_id`? |
| `app/banco.py` | Os índices são criados depois da carga inicial, e não junto com as tabelas. Por quê? |
| `app/routes/` | Nenhuma consulta mudou. |

Pergunta: *"e se o índice fosse `(criado_em, autor_id)`? Serviria para o feed?"*

## 3. O índice por dentro

A mesma consulta do feed da aula 01:

```bash
docker compose exec postgres psql -U mural -c "EXPLAIN ANALYZE
  SELECT * FROM posts WHERE autor_id IN (SELECT seguido_id FROM seguidores WHERE seguidor_id = 42)
  ORDER BY criado_em DESC LIMIT 20"
docker compose exec postgres psql -U mural -c "\di+"
```

👉 **Observe:** o plano da consulta e o tempo de execução, comparados com os da aula 01. E o tamanho dos índices no disco.

Agora o feed de quem segue muita gente, e uma página bem funda:

```bash
docker compose exec postgres psql -U mural -c "SELECT seguidor_id, count(*) FROM seguidores GROUP BY 1 ORDER BY 2 DESC LIMIT 1"
curl -s -o /dev/null -w "%{time_total}s\n" "localhost:8000/feed?usuario_id=<esse usuário>"
curl -s -o /dev/null -w "%{time_total}s\n" "localhost:8000/feed?usuario_id=<esse usuário>&pagina=50"
```

Pergunta: *"se índice é tão bom, por que não criar um em todas as colunas?"*

## 4. O dia em que um post viralizou

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/viral.js
xdg-open relatorios/viral.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 01? |
| A progressão | Em qual degrau as atendidas param de acompanhar as que chegam agora? |
| A velocidade de cada endpoint | Qual endpoint mais ganhou com os índices? |

👉 **Observe também:** no `docker compose stats`, a CPU do Postgres e a das réplicas do app. O banco continua sendo o limite?

Conte de novo as consultas de uma página do feed, como na aula 01:

```bash
docker compose exec postgres psql -U mural -c "ALTER SYSTEM SET log_statement = 'all'" -c "SELECT pg_reload_conf()"
curl -s -o /dev/null "localhost:8000/feed?usuario_id=42"
docker compose exec postgres psql -U mural -c "ALTER SYSTEM RESET log_statement" -c "SELECT pg_reload_conf()"
docker compose logs postgres --since 1m | grep -c "LOG:  execute"
```

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- O que limita o Mural agora?
- Os índices mudaram quantas consultas uma página do feed faz?
- Cada curtida nova é uma linha a mais. O que acontece com o total do post viral?

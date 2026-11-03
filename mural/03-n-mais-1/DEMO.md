# Mural · Aula 03: O N+1

> **Objetivo:** com os índices, o banco ficou rápido e o app virou o gargalo.
> Mostrar o problema mais comum de quem usa ORM, o N+1, e como montar uma
> página com poucas consultas, sem peça nova e com o mesmo hardware.

```
            ┌──────────────────────────┐   poucas   ┌───────────────────────────┐
 usuário ──▶│  Mural (1 processo)      │──────────▶ │ Postgres                  │
            │  FastAPI síncrono + ORM  │  consultas │ com os índices da 02      │
            │  1 CPU / 1 GB            │            │ 1 CPU / 1 GB              │
            └──────────────────────────┘            └───────────────────────────┘
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`mural/03-n-mais-1/`).

```bash
docker compose -f ../02-indices/docker-compose.yml down -v     # as etapas usam os mesmos nomes
docker compose up -d --build --wait
```

Rode o teste das etapas anteriores antes da aula: o relatório desta etapa compara com o último resultado delas.
Rode também o teste desta etapa uma vez: logo depois da subida, o banco ainda não tem nada na memória.

---

## 1. Onde a 02 parou

Abra `../02-indices/relatorios/viral.html` e relembre o `docker compose stats` daquela rodada.

Pergunta para a turma: *"o banco ficou rápido. Então por que o Mural não aguentou mais?"*

Pergunta: *"o que é o N+1? De onde vem esse nome?"*

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `app/routes/esquemas.py` | `posts_out`: as curtidas da página inteira numa consulta só, agrupada por post |
| `app/routes/feed.py` | `joinedload(Post.autor)`: o autor vem junto com o post. E no perfil, por que não precisa? |
| `app/routes/posts.py` | Os autores dos comentários, também de uma vez |

Pergunta: *"o ORM fazia as consultas escondido. Como dá para perceber o N+1 olhando só o código?"*

## 3. Contando as consultas

Ligue o log do Postgres, abra uma página do feed e desligue, como nas aulas anteriores:

```bash
docker compose exec postgres psql -U mural -c "ALTER SYSTEM SET log_statement = 'all'" -c "SELECT pg_reload_conf()"
curl -s -o /dev/null "localhost:8000/feed?usuario_id=42"
docker compose exec postgres psql -U mural -c "ALTER SYSTEM RESET log_statement" -c "SELECT pg_reload_conf()"
docker compose logs postgres --since 1m | grep "LOG:  execute"
```

👉 **Observe:** quantas consultas são agora, e como ficou a consulta do autor (procure o `JOIN`).

## 4. O dia em que um post viralizou

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/viral.js
xdg-open relatorios/viral.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 02? O ganho foi maior ou menor que o dos índices? |
| A progressão | Em qual degrau as atendidas param de acompanhar as que chegam agora? |
| A velocidade de cada endpoint | Qual endpoint ficou mais rápido? |

👉 **Observe também:** no `docker compose stats`, a CPU do app e do Postgres. Quem chega no limite primeiro agora?

Se o banco voltou a ser o gargalo, olhe de perto a consulta do feed:

```bash
docker compose exec postgres psql -U mural -c "EXPLAIN (ANALYZE, BUFFERS)
  SELECT * FROM posts WHERE autor_id IN (SELECT seguido_id FROM seguidores WHERE seguidor_id = 42)
  ORDER BY criado_em DESC LIMIT 20"
```

👉 **Observe:** quantas linhas o índice devolve (`rows` × `loops`) para o feed mostrar 20.

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- O que limita o Mural agora?
- Para mostrar 20 posts, quantos o banco precisa ler? E se eu seguir uma celebridade que posta muito?
- As curtidas ainda são contadas na hora. O que acontece quando um post tem milhões?

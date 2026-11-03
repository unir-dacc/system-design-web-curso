# Mural · Aula 04: A consulta do feed e a paginação

> **Objetivo:** depois do N+1, o banco voltou a ser o gargalo, e quem pesa é a
> consulta do feed. Mostrar que ter o índice não basta: a consulta precisa ser
> escrita de um jeito que deixe o índice trabalhar. E trocar o `OFFSET` pela
> paginação por cursor. Sem peça nova e com o mesmo hardware.

```
            ┌──────────────────────────┐   feed com   ┌───────────────────────────┐
 usuário ──▶│  Mural (1 processo)      │────────────▶ │ Postgres                  │
            │  FastAPI síncrono + ORM  │   LATERAL    │ os mesmos índices da 02   │
            │  1 CPU / 1 GB            │   + cursor   │ 1 CPU / 1 GB              │
            └──────────────────────────┘              └───────────────────────────┘
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`mural/04-paginacao/`).

```bash
docker compose -f ../03-n-mais-1/docker-compose.yml down -v     # as etapas usam os mesmos nomes
docker compose up -d --build --wait
```

Rode o teste das etapas anteriores antes da aula: o relatório desta etapa compara com o último resultado delas.
Rode também o teste desta etapa uma vez: logo depois da subida, o banco ainda não tem nada na memória.

---

## 1. Onde a 03 parou

Abra `../03-n-mais-1/relatorios/viral.html` e relembre o `EXPLAIN` do feed do fim daquela aula.

Pergunta para a turma: *"para mostrar 20 posts, quantos o banco lia? De onde vinham os outros?"*

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `app/routes/feed.py` | O feed: os 20 mais recentes de **cada** pessoa que eu sigo (`LATERAL`), e só depois os 20 mais novos de todos |
| `app/routes/feed.py` | A próxima página: `antes_de`, o `criado_em` do último post visto, no lugar do número da página |
| `app/modelos.py` | Nenhum índice novo. |

Pergunta: *"por que pegar 20 de cada pessoa garante que os 20 mais novos de todos estão entre eles?"*

Pergunta: *"com o cursor, dá para pular direto para a página 30? Isso é um problema num feed?"*

## 3. As duas consultas lado a lado

Escolha quem segue mais gente e compare a consulta da 03 com a desta aula:

```bash
docker compose exec postgres psql -U mural -c "SELECT seguidor_id, count(*) FROM seguidores GROUP BY 1 ORDER BY 2 DESC LIMIT 1"

docker compose exec postgres psql -U mural -c "EXPLAIN (ANALYZE, BUFFERS)
  SELECT * FROM posts WHERE autor_id IN (SELECT seguido_id FROM seguidores WHERE seguidor_id = <esse usuário>)
  ORDER BY criado_em DESC LIMIT 20"

docker compose exec postgres psql -U mural -c "EXPLAIN (ANALYZE, BUFFERS)
  SELECT p.* FROM seguidores s
  CROSS JOIN LATERAL (SELECT * FROM posts WHERE autor_id = s.seguido_id ORDER BY criado_em DESC LIMIT 20) p
  WHERE s.seguidor_id = <esse usuário>
  ORDER BY p.criado_em DESC LIMIT 20"
```

👉 **Observe:** em cada plano, quantas linhas saem do índice (`rows` × `loops`), os `Buffers` e o tempo de execução. Procure o `Index Scan Backward`.

Agora a paginação, no perfil de quem mais publica. A página 50 do jeito antigo (`OFFSET`) e do jeito novo (o cursor):

```bash
docker compose exec postgres psql -U mural -c "SELECT autor_id, count(*) FROM posts GROUP BY 1 ORDER BY 2 DESC LIMIT 1"

docker compose exec postgres psql -U mural -c "EXPLAIN ANALYZE
  SELECT * FROM posts WHERE autor_id = <esse autor> ORDER BY criado_em DESC OFFSET 980 LIMIT 20"

docker compose exec postgres psql -U mural -c "SELECT criado_em FROM posts WHERE autor_id = <esse autor> ORDER BY criado_em DESC OFFSET 979 LIMIT 1"
docker compose exec postgres psql -U mural -c "EXPLAIN ANALYZE
  SELECT * FROM posts WHERE autor_id = <esse autor> AND criado_em < '<o criado_em acima>' ORDER BY criado_em DESC LIMIT 20"
```

E no Mural, a página seguinte do feed:

```bash
curl -s "localhost:8000/feed?usuario_id=42" | grep -o '"criado_em":"[^"]*"' | tail -1
curl -s -G "localhost:8000/feed" --data-urlencode "usuario_id=42" --data-urlencode "antes_de=<o criado_em acima>"
```

Pergunta: *"com `OFFSET`, a página 50 custa o mesmo que a primeira? E com o cursor?"*

## 4. O dia em que um post viralizou

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/viral.js
xdg-open relatorios/viral.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 03? Nenhum índice novo, nenhuma máquina nova: de onde veio a diferença? |
| A progressão | Em qual degrau as atendidas param de acompanhar as que chegam agora? |
| A velocidade de cada endpoint | O feed ainda é o endpoint mais lento? |

👉 **Observe também:** no `docker compose stats`, a CPU do app e do Postgres. Quem chega no limite primeiro agora?

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- O que limita o Mural agora?
- O feed lê no máximo 20 posts de cada pessoa que eu sigo. E quem segue milhares de pessoas?
- As curtidas ainda são contadas na hora. O post viral recebe milhares por minuto: quanto custa contar?

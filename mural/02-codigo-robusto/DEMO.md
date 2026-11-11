# Mural · Aula 02: O código robusto

> **Objetivo:** sair do código ingênuo da 01 para um código que usa bem o banco,
> sem nenhuma peça nova e com o mesmo Postgres. Cinco mudanças, todas no código
> e no esquema: os índices certos, o fim do N+1, uma consulta do feed que deixa
> o índice trabalhar, a paginação por cursor e o total de curtidas guardado no
> próprio post. E medir quanto elas valem juntas.

```
            ┌─────┐    ┌─────────────────────────────┐   1 consulta   ┌───────────────────────────────┐
 usuário ──▶│nginx│───▶│ Mural · 4 réplicas          │──────────────▶ │ Postgres                      │
            └─────┘    │ FastAPI async + ORM         │   por página   │ + posts (autor_id, criado_em) │
                       │ CPU sem limite              │   do feed      │ + comentarios (post_id, ...)  │
                       └─────────────────────────────┘                │ + posts.curtidas              │
                                                                      │ 1 CPU / 1 GB                  │
                                                                      └───────────────────────────────┘
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`mural/02-codigo-robusto/`).

```bash
docker compose up -d --build --wait     # aproveita o banco da etapa 01
```

A 02 usa os mesmos nomes da 01 e aproveita a rede que já está no banco: ao subir, ela só
acrescenta o total de curtidas nos posts e os índices, em alguns segundos.

Rode o teste da etapa 01 antes da aula: o relatório desta etapa compara com o último resultado dela.

---

## 1. O que a 01 mostrou

Abra `../01-ponto-de-partida/relatorios/viral.html`.

Pergunta para a turma: *"o app tinha CPU de sobra e o banco ficou no limite. O que o banco estava fazendo?
Quantas consultas uma página do feed fazia?"*

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `app/modelos.py` | Os dois índices compostos. Por que `(autor_id, criado_em)` e não só `autor_id`? E a coluna `curtidas` no post |
| `app/banco.py` | Os índices são criados depois da carga inicial, e não junto com as tabelas. Por quê? |
| `app/routes/feed.py` | O feed: os 20 mais recentes de **cada** pessoa que eu sigo (`LATERAL`), e o autor na mesma consulta (`JOIN`). A próxima página pelo cursor (`antes_de`) |
| `app/routes/esquemas.py` | `post_out` não consulta mais nada: o autor e o total já vêm prontos |
| `app/routes/posts.py` | A curtida: `ON CONFLICT DO NOTHING` em vez de consultar antes, e o total somado na mesma transação |

Pergunta: *"por que pegar 20 de cada pessoa garante que os 20 mais novos de todos estão entre eles?"*

Pergunta: *"por que `curtidas = curtidas + 1` no banco, e não ler o total, somar 1 no Python e gravar?"*

## 3. Cada mudança, de perto

### Os índices

```bash
docker compose exec postgres psql -U mural -c "\di+"
```

👉 **Observe:** quais índices existem agora, e quanto espaço cada um ocupa.

Pergunta: *"uma ForeignKey cria índice? E se índice é tão bom, por que não criar um em todas as colunas?"*

### O N+1

Conte as consultas de uma página do feed, como na aula 01:

```bash
docker compose exec postgres psql -U mural -c "ALTER SYSTEM SET log_statement = 'all'" -c "SELECT pg_reload_conf()"
curl -s -o /dev/null "localhost:8000/feed?usuario_id=42"
docker compose exec postgres psql -U mural -c "ALTER SYSTEM RESET log_statement" -c "SELECT pg_reload_conf()"
docker compose logs postgres --since 1m | grep "LOG:  execute"
```

👉 **Observe:** quantas consultas são agora, e como o autor aparece na consulta do feed (procure o `JOIN`).

### A consulta do feed

Escolha quem segue mais gente e compare a consulta da 01 com a desta aula:

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

### A paginação por cursor

A página 50 do perfil de quem mais publica, do jeito antigo (`OFFSET`) e do jeito novo (o cursor):

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

Pergunta: *"com `OFFSET`, a página 50 custa o mesmo que a primeira? E com o cursor? Com o cursor, dá para pular direto para a página 30?"*

### O total de curtidas

```bash
curl -s -X POST localhost:8000/posts/1/curtidas -H 'Content-Type: application/json' -d '{"usuario_id": 7}'; echo
curl -s -X POST localhost:8000/posts/1/curtidas -H 'Content-Type: application/json' -d '{"usuario_id": 7}'; echo
curl -s localhost:8000/admin/curtidas/1; echo
```

👉 **Observe:** o código HTTP de cada curtida, e se o total guardado no post bate com as linhas da tabela de curtidas.

## 4. O dia em que um post viralizou

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/viral.js
xdg-open relatorios/viral.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 01? Nenhuma peça nova, nenhum banco maior: de onde veio a diferença? |
| A progressão | Em qual degrau as atendidas param de acompanhar as que chegam agora? |
| A velocidade de cada endpoint | Qual endpoint mais ganhou? E as curtidas, que agora gravam duas coisas? |
| As curtidas | As curtidas gravadas no banco para o post viral e as que o Mural mostra batem? |

👉 **Observe também:** no `docker compose stats`, a CPU do Postgres e a das réplicas do app. O banco continua sendo o limite?

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- O código está bom. O que limita o Mural agora?
- Todas as curtidas do post viral somam na mesma linha da tabela de posts. O que acontece quando milhares chegam ao mesmo tempo?
- O feed lê no máximo 20 posts de cada pessoa que eu sigo. E quem segue milhares de pessoas?
- Daqui para a frente, o código não ajuda mais. O que mais dá para fazer com o mesmo banco?

# Encurtador · Aula 02: Consertos

> **Objetivo:** consertar o que a 01 fazia de mais ingênuo com o banco, sem
> nenhuma peça nova e com o mesmo hardware, e medir quanto cada conserto vale.

```
            ┌──────────────────────────┐        ┌───────────────────────┐
 usuário ──▶│  Encurtador (1 processo) │──────▶ │ Postgres              │
            │  FastAPI síncrono        │        │ + índice em "codigo"  │
            │  1 CPU / 1 GB            │        │ 1 CPU / 1 GB          │
            └──────────────────────────┘        └───────────────────────┘
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`encurtador/02-consertos/`).

```bash
docker compose -f ../01-monolito/docker-compose.yml down -v     # a 01 usa os mesmos nomes
docker compose up -d --build --wait
```

Rode o teste da etapa 01 antes da aula: o relatório desta etapa compara com o último resultado dela.

---

## 1. O que a 01 mostrou

Abra `../01-monolito/relatorios/movimento.html`.

Pergunta para a turma: *"quem chegou no limite primeiro: o app ou o banco? E o que o banco estava fazendo?"*

## 2. Os três consertos

| Arquivo | O que mostrar |
|---------|---------------|
| `app/banco.py` | O índice único em `codigo`. Por que ele é criado depois da carga inicial, e não antes? |
| `app/banco.py` e `app/routes/links.py` | `codigo_valido`: o código é conferido antes de ir ao banco. Como o Sqids sabe que um código foi inventado? |
| `app/db.py` e `app/main.py` | Os limites de tempo e o 503. Por que responder erro na hora pode ser melhor do que esperar? |

Pergunta: *"o índice é UNIQUE. O que ele garante, além de deixar a busca rápida?"*

## 3. O índice por dentro

```bash
docker compose exec postgres psql -U encurtador -c "EXPLAIN ANALYZE SELECT url FROM links WHERE codigo = 'zzzzzzz'"
docker compose exec postgres psql -U encurtador -c "\di+ links*"
```

👉 **Observe:** o plano da consulta e o tempo de execução, comparados com os da aula 01. E o tamanho do índice no disco.

Pergunta: *"se índice é tão bom, por que não criar um em todas as colunas?"*

## 4. Os robôs

```bash
curl -s -o /dev/null -w "%{http_code} em %{time_total}s\n" localhost:8000/zzzzzzz
curl -s -o /dev/null -w "%{http_code} em %{time_total}s\n" localhost:8000/<um código de verdade>
```

👉 **Observe:** o tempo da resposta para um código inventado e para um de verdade.

## 5. O dia em que o encurtador bombou

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/movimento.js
xdg-open relatorios/movimento.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 01? Em qual coluna o ganho aparece mais? |
| A progressão | Em qual degrau as atendidas param de acompanhar as que chegam agora? |
| A velocidade de cada endpoint | Qual endpoint ficou mais rápido? E os robôs? |
| Os cliques | Os cliques redirecionados e os contados batem? |

👉 **Observe também:** no `docker compose stats`, a CPU do app e do Postgres. Agora, quem chega no limite primeiro?

Pergunta: *"apareceram respostas 503? O que elas significam para quem clicou?"*

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- O que limita o encurtador agora?
- Todo clique ainda é uma escrita no banco. Isso apareceu no teste?
- O que acontece com a tabela e o índice quando o encurtador tiver 100 milhões de links?

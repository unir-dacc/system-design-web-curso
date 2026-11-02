# Encurtador · Aula 01: O monolito

> **Objetivo:** apresentar o encurtador funcionando e colocá-lo à prova no dia
> em que todo mundo resolve compartilhar links ao mesmo tempo.

```
            ┌──────────────────────────┐        ┌───────────────────────┐
 usuário ──▶│  Encurtador (1 processo) │──────▶ │ Postgres              │
            │  FastAPI síncrono        │        │ 1 milhão de links     │
            │  1 CPU / 1 GB            │        │ 1 CPU / 1 GB          │
            └──────────────────────────┘        └───────────────────────┘
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`encurtador/01-monolito/`).

```bash
docker compose down -v          # garante que começa do zero
docker compose up -d --build --wait
```

A primeira subida cria 1 milhão de links e leva alguns segundos.
Deixe abertas duas abas: http://localhost:8000/docs e um terminal com `docker compose stats`.

---

## 1. Tour pelo código

| Arquivo | O que mostrar |
|---------|---------------|
| `app/banco.py` | A tabela `links` e como o código curto nasce do número do link. Por que dois links nunca recebem o mesmo código? |
| `app/routes/links.py` | Criar, redirecionar, estatísticas. O redirecionamento acha o link e conta o clique numa instrução só |
| `app/main.py` | Por que a rota `/{codigo}` fica por último? |

Pergunta para a turma: *"de cada 100 acessos a um encurtador, quantos vocês acham que são cliques, e quantos são links novos?"*

## 2. O encurtador funcionando

```bash
curl -s -X POST localhost:8000/links -H 'Content-Type: application/json' -d '{"url": "https://www.unir.br"}'; echo

curl -s -i localhost:8000/<codigo> | head -3                 # use o código que veio acima
curl -s localhost:8000/links/<codigo>/estatisticas; echo
```

👉 **Observe:** o status do redirecionamento e o cabeçalho `location`. Rode o redirecionamento de novo e veja as estatísticas.

Pergunta: *"por que 302 e não 301? O que o navegador faria com um 301?"*

## 3. Olhando o banco por dentro

```bash
docker compose exec postgres psql -U encurtador -c "SELECT count(*), pg_size_pretty(pg_total_relation_size('links')) FROM links"
docker compose exec postgres psql -U encurtador -c "EXPLAIN ANALYZE SELECT url FROM links WHERE codigo = 'zzzzzzz'"
docker compose exec postgres psql -U encurtador -c "EXPLAIN ANALYZE SELECT url FROM links WHERE id = 123456"
```

👉 **Observe:** o plano de cada consulta (o que o Postgres fez para achar a linha) e o tempo de execução.

Pergunta: *"por que procurar pelo `id` é tão diferente de procurar pelo `codigo`, se a tabela é a mesma?"*

## 4. O dia em que o encurtador bombou

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/movimento.js
xdg-open relatorios/movimento.html
```

| Bloco | Perguntas |
|-------|-----------|
| Topo | Quantas requisições por segundo o encurtador aguenta? E no pico, quantas foram atendidas? |
| A progressão | Em qual degrau as atendidas param de acompanhar as que chegam? |
| A velocidade de cada endpoint | Qual endpoint é o mais lento? E os robôs, com códigos que não existem? |
| Os cliques | Quantos cliques foram redirecionados, e quantos o encurtador contou? |

👉 **Observe também:** no `docker compose stats`, a CPU do app e do Postgres. Quem chega no limite primeiro?

Pergunta: *"um robô que tenta um código que não existe custa mais ou menos para o banco do que um clique de verdade? Por quê?"*

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- Onde o encurtador passou o tempo?
- O que acontece com o banco quando a tabela de links dobrar de tamanho?
- Todo clique é uma escrita no banco. Isso é um problema?

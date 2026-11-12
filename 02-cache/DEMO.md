# Aula 02: Cache

> **Objetivo:** mostrar que a maior parte do trabalho do Ingressa era refazer,
> para cada usuário, uma resposta igual para todo mundo, e o que muda quando ela
> é montada uma vez e guardada.

```
            ┌──────────────────────────┐        ┌───────────────────────┐
 usuário ──▶│  Ingressa (1 processo)   │──────▶ │ Sistema do cinema     │
            │  FastAPI síncrono        │        └───────────────────────┘
            │  1 CPU / 1 GB            │──────▶ ┌───────────────────────┐
            └──────┬──────────────┬────┘        │ Gateway de pagamento  │
                   │              │             └───────────────────────┘
             ┌─────▼─────┐  ┌─────▼─────┐       ┌───────────────────────┐
             │ Postgres  │  │  Redis    │       │ Mailpit (SMTP falso)  │
             │ 0.75 CPU  │  │ 0.25 CPU  │       └───────────────────────┘
             └───────────┘  └───────────┘
```

O orçamento é o mesmo da etapa 01: 2 CPUs e 2 GB. O Redis não ganhou hardware novo: o Postgres cedeu uma parte do dele.

O diagrama desta etapa está em `arquitetura.excalidraw`, nesta pasta: abra em https://excalidraw.com
(menu ☰ → Abrir, ou arraste o arquivo para a página) ou com a extensão Excalidraw do VS Code, e desenhe
por cima durante a aula. A peça nova da etapa está em amarelo.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`02-cache/`).

```bash
docker compose down -v          # garante que começa do zero
docker compose up -d --build --wait
```

Rode a estreia da etapa 01 antes da aula: o relatório desta etapa compara com o último resultado dela.

---

## 1. De volta ao relatório da 01

Abra `../01-monolito/relatorios/estreia.html` e relembre o que o público faz: a maioria só olha a programação e o mapa.

Pergunta para a turma: *"a programação que eu vejo é diferente da que vocês veem? E o mapa da sessão das 20h?"*

Pergunta: *"se mil pessoas abrem a programação no mesmo segundo, quantas vezes o Ingressa precisa montá-la?"*

## 2. O que mudou no código

| Arquivo | O que mostrar |
|---------|---------------|
| `app/cache.py` | Guardar a resposta pronta, com prazo de validade. E a trava: por que só uma requisição monta a resposta? |
| `app/routes/catalogo.py` | A programação e o mapa vêm do cache. As funções `montar_` só rodam quando não há cópia |
| `app/compra.py` | `mapa_mudou`: quando uma compra mexe nos assentos, a cópia do mapa é apagada |
| `app/config.py` | Quanto tempo cada resposta fica guardada. Por que a programação dura mais que o mapa? |
| `docker-compose.yml` | O Redis entrou, e o orçamento foi dividido |

Pergunta: *"o que acontece se a cópia do mapa ficar velha? Alguém consegue comprar um assento que já foi vendido?"*

## 3. Vendo o cache funcionar

```bash
curl -s -X POST localhost:8000/admin/reset > /dev/null

curl -s -o /dev/null -w '%{time_total}s\n' 'localhost:8000/sessoes?filme_id=1'   # repita algumas vezes
docker compose exec redis redis-cli keys '*'
docker compose exec redis redis-cli ttl 'sessoes:filme:1'
```

👉 **Observe:** o tempo da primeira resposta e das seguintes, e as chaves guardadas no Redis.

Agora compre um assento e veja o mapa:

```bash
curl -s localhost:8000/sessoes/7/assentos > /dev/null
docker compose exec redis redis-cli exists 'mapa:7'

curl -s -X POST localhost:8000/pedidos -H 'Content-Type: application/json' -d '{
  "sessao_id": 7, "nome": "Maria", "cpf": "529.982.247-25", "email": "maria@exemplo.com",
  "cartao_token": "tok_aprovado", "itens": [{"assento": "A1"}]
}' > /dev/null

docker compose exec redis redis-cli exists 'mapa:7'
curl -s localhost:8000/sessoes/7/assentos | grep -o '{"codigo":"A1","status":"[a-z]*"}'
```

👉 **Observe:** se a cópia do mapa existia antes e depois da compra, e o status do A1.

## 4. A estreia

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 01? Em qual coluna o ganho aparece mais? |
| A subida | Em qual degrau a linha fica vermelha agora? O que piora primeiro: as páginas ou a compra? |
| O pico: cada público | Quem ganhou mais com o cache: os curiosos ou os compradores? Por quê? |
| A espera e as metas | Quais metas passaram agora e não passavam antes? |

👉 **Observe também:** no `docker compose stats`, a CPU do Ingressa, do Postgres e do Redis. O Redis precisou de muito?

Pergunta: *"o cache ajudou a compra? O que a compra faz que não dá para guardar pronto?"*

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

## 5. O prazo de validade

Experimente outra validade para o mapa e rode a estreia de novo:

```bash
MAPA_TTL_S=1 docker compose up -d ingressa
docker compose run --rm --service-ports k6 run /scripts/estreia.js
MAPA_TTL_S=5 docker compose up -d ingressa     # volta ao padrão
```

👉 **Observe:** a capacidade e o tempo das páginas.

Pergunta: *"se o mapa é apagado a cada compra, para que serve a validade? E se ela fosse de 1 hora?"*

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

Deixe no quadro as perguntas que a turma levantou. Elas guiam as próximas aulas:

- O que limita o Ingressa agora?
- Por que a compra não ficou mais rápida?
- O que acontece com o Ingressa se o Redis cair?

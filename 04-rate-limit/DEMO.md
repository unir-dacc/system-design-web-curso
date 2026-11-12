# Aula 04: Rate limit, a proteção na porta

> **Objetivo:** mostrar que, quando chega mais gente do que o Ingressa aguenta,
> recusar o excesso na hora é melhor do que deixar todo mundo entrar e atender
> todo mundo mal.

```
                         limites por endpoint
                         (o que passa, recebe 429)
                                 │      ┌──────────────────────┐
            ┌──────────────┐     ▼  ┌──▶│ Ingressa (backend 1) │──┐
 usuário ──▶│    Nginx     │────────┤   └──────────────────────┘  ├──▶ Postgres, Redis,
            │ rate limit   │        │   ┌──────────────────────┐  │    cinema, gateway
            └──────────────┘        └──▶│ Ingressa (backend 2) │──┘
                                        └──────────────────────┘
```

O hardware e a divisão são os mesmos da etapa 03. O que muda é só a configuração do Nginx.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`04-rate-limit/`).

```bash
docker compose down -v          # garante que começa do zero
docker compose up -d --build --wait
```

Rode a estreia das etapas anteriores antes da aula: o relatório desta etapa compara com o último resultado delas.

---

## 1. Onde a 03 parou

Abra `../03-nginx/relatorios/estreia.html` e olhe a progressão das vendas e o pico.

Pergunta para a turma: *"no pico, o Ingressa da 03 recebeu todo mundo. Quantos foram atendidos? Quanto tempo esperaram?"*

Pergunta: *"numa loja lotada, o que é melhor: deixar todo mundo entrar ou controlar a entrada na porta?"*

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `nginx/templates/ingressa.conf.template` | O `limit_conn` de cada endpoint: quantas requisições podem estar em andamento ao mesmo tempo. E o `@muita_gente`: o que o barrado recebe |
| `docker-compose.yml` | Os limites (`MAX_*`) de cada endpoint. Por que a compra tem um limite bem menor que a programação? |

Pergunta: *"o limite é de requisições em andamento, e não por segundo. O que aconteceria com um limite por segundo se o gateway de pagamento ficasse mais lento?"*

Pergunta: *"por que o limite é para o Ingressa inteiro, e não por usuário (por IP)? Quando um limite por IP faria sentido?"*

## 3. A porta funcionando

```bash
# deixa só 2 compras em andamento e dispara 8 de uma vez
MAX_COMPRAS_SIMULTANEAS=2 docker compose up -d nginx
curl -s -X POST localhost:8000/admin/reset > /dev/null
for i in $(seq 8); do
  curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" -X POST localhost:8000/pedidos -H 'Content-Type: application/json' \
    -d "{\"sessao_id\":8,\"nome\":\"Maria\",\"cpf\":\"52998224725\",\"email\":\"m@ex.com\",\"cartao_token\":\"tok_aprovado\",\"itens\":[{\"assento\":\"C$i\"}]}" &
done | sort
docker compose up -d nginx                    # volta ao padrão
```

👉 **Observe:** quantas compras passaram, quantas foram barradas, e quanto tempo cada uma esperou.

Pergunta: *"o que o usuário barrado vê? O que um site de verdade mostraria para ele?"*

## 4. A estreia

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

| Bloco | Perguntas |
|-------|-----------|
| A progressão das vendas | Depois do limite, as vendas caem como antes ou se mantêm? |
| O ganho de cada etapa | O que mudou em relação à 03? Em qual coluna? |
| O pico: cada público | Quem foi atendido, foi bem atendido? E quem não foi? |
| O pico: a velocidade de cada endpoint | Quais endpoints mais barraram? Faz sentido? |
| A espera e as metas | Quais metas passaram agora e não passavam antes? |

👉 **Observe também:** no `docker compose stats`, a CPU dos backends durante o pico. Ela ainda bate no teto?

Pergunta: *"recusar gente na porta parece pior do que deixar todo mundo entrar. Por que pode ser melhor para quem está dentro? E para quem foi barrado?"*

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

## 5. Qual é o limite certo?

```bash
MAX_COMPRAS_SIMULTANEAS=10 docker compose up -d nginx      # porta estreita
docker compose run --rm --service-ports k6 run /scripts/estreia.js

MAX_COMPRAS_SIMULTANEAS=1000 docker compose up -d nginx    # porta aberta, como se não houvesse limite
docker compose run --rm --service-ports k6 run /scripts/estreia.js

docker compose up -d nginx                                  # volta ao padrão
```

👉 **Observe:** na subida, a partir de qual degrau aparecem barrados. No pico, quantos compradores conseguiram comprar e quanto tempo esperaram.

Pergunta: *"o que acontece se o limite for estreito demais? E largo demais? Como escolher o número?"*

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

- Quem foi barrado na porta: o que um site de verdade faria com essa pessoa?
- O que limita o Ingressa agora?
- O que acontece com uma compra se o backend cair no meio do pagamento?

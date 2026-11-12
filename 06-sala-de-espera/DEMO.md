# Aula 06: Sala de espera

> **Objetivo:** mostrar que, quando a procura passa do que o Ingressa aguenta,
> dá para não perder ninguém: em vez de recusar o excesso, cada pessoa recebe
> uma senha e entra quando chega a vez dela.

```
            ┌───────────────────────┐   senha   ┌──────────────────────┐
 usuário ──▶│  Sala de espera       │──────────▶│ Porteiro (no worker) │
            │  POST /sala           │◀──────────│ libera N senhas/s    │
            │  GET /sala/{senha}    │   passe   └──────────────────────┘
            └───────────┬───────────┘
                        │ com o passe (X-Passe)
                        ▼
            ┌──────────────┐        ┌──────────────────────┐
            │    Nginx     │───────▶│ Ingressa (2 backends)│──▶ fila ──▶ worker
            └──────────────┘        └──────────────────────┘
```

O orçamento é o mesmo: 2 CPUs e 2 GB. Nada novo foi adicionado: a sala vive no Redis, e o porteiro é uma thread do worker.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`06-sala-de-espera/`).

```bash
docker compose down -v          # garante que começa do zero
docker compose up -d --build --wait
```

Rode a estreia das etapas anteriores antes da aula: o relatório desta etapa compara com o último resultado delas.

---

## 1. Onde a 05 parou

Abra `../05-fila/relatorios/estreia.html`, no pico.

Pergunta para a turma: *"quem foi barrado na porta (429) fez o quê? Voltou depois?"*

Pergunta: *"num cartório lotado, o que acontece com quem chega? E num site de ingresso de show grande?"*

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `app/sala.py` | As senhas e o contador de liberadas no Redis. O que o porteiro faz a cada 0,2 s? |
| `app/routes/sala.py` | Entrar na sala, perguntar a vez (com `Retry-After`) e o `exige_passe` |
| `app/routes/catalogo.py` e `app/routes/pedidos.py` | Quais rotas agora exigem passe? |
| `app/worker.py` | O porteiro, uma thread a mais no worker |
| `docker-compose.yml` | `LIBERAR_POR_SEGUNDO`: quantas pessoas entram por segundo |

Pergunta: *"por que o passe é assinado? O que um robô cambista faria se não fosse?"*

Pergunta: *"o servidor diz em quantos segundos perguntar de novo. Por que não deixar cada um perguntar quando quiser?"*

## 3. A sala funcionando

```bash
curl -s -X POST localhost:8000/admin/reset > /dev/null

curl -s -o /dev/null -w "sem passe: %{http_code}\n" 'localhost:8000/sessoes?filme_id=1'

curl -s -X POST localhost:8000/sala; echo           # pega uma senha
curl -s localhost:8000/sala/1; echo                 # pergunta a vez (repita até liberar)

# use o passe que veio na resposta
curl -s -o /dev/null -w "com passe: %{http_code}\n" -H 'X-Passe: <cole o passe aqui>' 'localhost:8000/sessoes?filme_id=1'
```

👉 **Observe:** o que acontece sem passe, a posição na fila e o `Retry-After` (use `curl -i` para ver os cabeçalhos).

Agora deixe a sala encher: pare o porteiro e pegue algumas senhas.

```bash
docker compose stop worker
for i in $(seq 5); do curl -s -X POST localhost:8000/sala; echo; done
docker compose start worker
```

👉 **Observe:** as pessoas na frente e a espera estimada de cada senha.

## 4. A estreia

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 05? Em qual coluna? |
| A progressão das vendas | Depois do limite, as vendas caem, se mantêm ou continuam acompanhando a procura? |
| O pico: cada público | Quantos passaram pela sala? Quantos desistiram de esperar? |
| A espera e as metas | Quanto tempo as pessoas esperaram a vez? Isso é aceitável numa estreia? |

👉 **Observe também:** no `docker compose stats`, a CPU dos backends durante o pico. Ela ainda bate no teto?

Anote o número do topo e compare com as etapas anteriores.

## 5. O ritmo do porteiro

```bash
LIBERAR_POR_SEGUNDO=30 docker compose up -d worker      # porteiro lento
docker compose run --rm --service-ports k6 run /scripts/estreia.js

LIBERAR_POR_SEGUNDO=150 docker compose up -d worker     # porteiro apressado
docker compose run --rm --service-ports k6 run /scripts/estreia.js

docker compose up -d worker                              # volta ao padrão
```

👉 **Observe:** a espera na sala, os barrados na porta e o tempo das páginas em cada caso.

Pergunta: *"o que acontece se o porteiro liberar gente demais? E de menos? Quem deveria decidir esse número?"*

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

Deixe no quadro as perguntas que a turma levantou:

- A sala não aumentou a capacidade do Ingressa. Então o que ela melhorou?
- Quanto tempo uma pessoa aceita esperar numa sala de espera? O que mostrar para ela enquanto isso?
- Olhando para trás: qual etapa deu o maior ganho? Qual foi a mais barata?

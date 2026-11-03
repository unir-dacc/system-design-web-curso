# Encurtador · Aula 03: Nginx na frente de 3 backends

> **Objetivo:** depois dos consertos, o gargalo saiu do banco e foi para o app.
> Mostrar como colocar a CPU onde ela faz falta, sem hardware novo, e o que isso
> começa a cobrar do banco.

```
                                 ┌──────────────────────┐
                            ┌──▶ │ backend 1 (0.4 CPU)  │──┐
            ┌──────────┐    │    └──────────────────────┘  │     ┌───────────────────┐
 usuário ──▶│  Nginx   │────┼──▶ │ backend 2 (0.4 CPU)  │──┼───▶ │ Postgres          │
            │ 0.2 CPU  │    │    └──────────────────────┘  │     │ 0.6 CPU           │
            └──────────┘    └──▶ │ backend 3 (0.4 CPU)  │──┘     └───────────────────┘
                                 └──────────────────────┘
```

O orçamento é o mesmo: 2 CPUs e 2 GB. O Postgres cedeu a CPU que não usava.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`encurtador/03-nginx/`).

```bash
docker compose -f ../02-consertos/docker-compose.yml down -v     # as etapas usam os mesmos nomes
docker compose up -d --build --wait
```

A primeira subida cria o milhão de links e leva alguns minutos. Rode o teste das etapas anteriores antes da aula: o relatório desta etapa compara com o último resultado delas.

---

## 1. Onde a 02 parou

Abra `../02-consertos/relatorios/movimento.html` e relembre o `docker compose stats` daquela rodada.

Pergunta para a turma: *"o banco estava usando quanto da CPU dele? E o app?"*

Pergunta: *"um processo Python consegue usar mais de 1 CPU? Por quê?"*

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `docker-compose.yml` | O Nginx na frente, o app com `replicas: 3` e a nova divisão do orçamento. De onde saiu a CPU? |
| `nginx/nginx.conf` | O `upstream`: como o Nginx encontra os backends e alterna entre eles |
| `app/main.py` | Os três backends sobem juntos, e só um cria os links. Como os outros esperam? |

Pergunta: *"cada backend abre até 40 conexões com o banco. Quantas são com 3 backends? Quantas o Postgres aceita?"*

```bash
docker compose exec postgres psql -U encurtador -c "SHOW max_connections"
docker compose exec postgres psql -U encurtador -c "SELECT count(*) FROM pg_stat_activity"
```

## 3. Vendo o Nginx dividir o trabalho

```bash
for i in $(seq 9); do curl -s -o /dev/null localhost:8000/<um código de verdade>; done
docker compose logs app | grep 'GET /<o mesmo código>' | cut -c1-12 | sort | uniq -c
```

👉 **Observe:** quantos cliques cada backend atendeu.

## 4. O dia em que o encurtador bombou

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/movimento.js
xdg-open relatorios/movimento.html
```

Durante o teste, num terceiro terminal, acompanhe as conexões abertas no banco:

```bash
watch -n2 'docker compose exec postgres psql -U encurtador -tAc "SELECT count(*) FROM pg_stat_activity"'
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 02? |
| A progressão | Até onde as atendidas acompanham as que chegam agora? |
| A velocidade de cada endpoint | Algum endpoint piorou? |
| Os cliques | Os cliques redirecionados e os contados batem? |

👉 **Observe também:** no `docker compose stats`, a CPU dos backends e do Postgres. E o número de conexões no banco ao longo do teste.

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- O que limita o encurtador agora?
- E se fossem 10 backends? O que aconteceria com as conexões do banco?
- Agora são centenas de cliques por segundo. Quanto disso é escrita no banco?

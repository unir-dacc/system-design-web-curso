# Aula 03: Nginx na frente de 2 backends

> **Objetivo:** mostrar que, com o mesmo hardware, dá para atender mais gente
> colocando a CPU onde está o gargalo, e que um balanceador de carga deixa o
> Ingressa crescer em cópias e proteger os backends na porta.

```
                                    ┌──────────────────────┐
                               ┌──▶ │ Ingressa (backend 1) │──┐     ┌───────────────────────┐
            ┌──────────────┐   │    │ 0.65 CPU             │  ├───▶ │ Cinema, gateway,      │
 usuário ──▶│    Nginx     │───┤    └──────────────────────┘  │     │ Mailpit               │
            │   0.2 CPU    │   │    ┌──────────────────────┐  │     └───────────────────────┘
            └──────────────┘   └──▶ │ Ingressa (backend 2) │──┤
                                    │ 0.65 CPU             │  │
                                    └──────────────────────┘  │
                                  ┌───────────┐  ┌──────────┐ │
                                  │ Postgres  │◀─┤  Redis   │◀┘
                                  │ 0.25 CPU  │  │ 0.25 CPU │
                                  └───────────┘  └──────────┘
```

O orçamento é o mesmo das etapas anteriores: 2 CPUs e 2 GB. Só mudou a divisão.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`03-nginx/`).

```bash
docker compose down -v          # garante que começa do zero
docker compose up -d --build --wait
```

Rode a estreia das etapas 01 e 02 antes da aula: o relatório desta etapa compara com o último resultado delas.

---

## 1. Onde a 02 parou

Rode a estreia da 02 com `docker compose stats` aberto (ou relembre o que a turma anotou).

Pergunta para a turma: *"quanto da CPU de cada peça foi usada? Quem estava no limite e quem estava sobrando?"*

Pergunta: *"se o Ingressa está no limite de 1 CPU, por que não usar mais? O que impede um processo Python de usar 2 CPUs?"*

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `docker-compose.yml` | O Nginx entrou na frente. O Ingressa tem `replicas: 2`. A nova divisão do orçamento: de onde saiu a CPU? |
| `nginx/templates/ingressa.conf.template` | O `upstream`: como o Nginx sabe quais são os backends e alterna entre eles. E o `limit_conn`: quantas compras e páginas podem estar em andamento ao mesmo tempo |
| `app/main.py` | Os dois backends sobem juntos: por que precisam de uma trava para criar o catálogo? |
| `app/cache.py` | Nada mudou. Por que o cache precisa estar no Redis, e não na memória de cada backend? |

Pergunta: *"um usuário abre o mapa no backend 1 e compra no backend 2. Isso dá problema?"*

## 3. Vendo o Nginx dividir o trabalho

```bash
curl -s -X POST localhost:8000/admin/reset > /dev/null
for i in $(seq 10); do curl -s -o /dev/null localhost:8000/sessoes/7/assentos; done
docker compose logs ingressa | grep 'GET /sessoes/7/assentos' | cut -c1-12 | sort | uniq -c
```

👉 **Observe:** quantas requisições cada backend atendeu.

## 4. A estreia

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 02? O ganho foi do tamanho que vocês esperavam? |
| A subida | Em qual degrau a linha fica vermelha agora? O que piora primeiro: as páginas ou a compra? |
| O pico: cada público | Curiosos e compradores conseguiram o que queriam? |

👉 **Observe também:** no `docker compose stats`, a CPU de cada backend, do Nginx e do Postgres. O Nginx precisou de muito para repassar tudo?

Pergunta: *"o hardware é o mesmo da 01. De onde veio o ganho desde lá?"*

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

## 5. Um backend cai no meio da estreia

Rode a estreia de novo e, quando ela estiver na subida, derrube um backend:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
docker stop ingressa-ingressa-2          # em outro terminal, no meio da subida
docker start ingressa-ingressa-2         # depois de alguns degraus
```

👉 **Observe:** no painel do k6, o que acontece com os erros e o tempo das páginas quando o backend cai, e quando ele volta.

Pergunta: *"o que os usuários do backend que caiu perderam? E o que não perderam?"*

## 6. Mais backends?

```bash
docker compose up -d --scale ingressa=3
for i in $(seq 30); do curl -s -o /dev/null localhost:8000/sessoes/7/assentos; done
docker compose logs --since 1m ingressa | grep 'GET /sessoes/7/assentos' | cut -c1-12 | sort | uniq -c
docker compose ps
```

👉 **Observe:** o backend novo recebe requisições? E depois de `docker compose restart nginx`?

Pergunta: *"como o Nginx descobre que existe um backend novo?"*

Pergunta: *"com 3 backends, cada um ainda teria 0,65 CPU? O que precisaria mudar para continuar dentro do orçamento? Valeria a pena?"*

```bash
docker compose up -d --scale ingressa=2     # volta ao padrão
```

## 7. A porta: quem entra é bem atendido

O Nginx deixa entrar no máximo 60 compras e 80 páginas em andamento ao mesmo tempo. Quem passa disso recebe na hora um "muita gente agora, tente de novo" (429).

```bash
# deixa só 2 compras em andamento e dispara 8 de uma vez
MAX_COMPRAS_SIMULTANEAS=2 docker compose up -d nginx
curl -s -X POST localhost:8000/admin/reset > /dev/null
for i in $(seq 8); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/pedidos -H 'Content-Type: application/json' \
    -d "{\"sessao_id\":8,\"nome\":\"Maria\",\"cpf\":\"52998224725\",\"email\":\"m@ex.com\",\"cartao_token\":\"tok_aprovado\",\"itens\":[{\"assento\":\"C$i\"}]}" &
done | sort | uniq -c
docker compose up -d nginx                    # volta ao padrão
```

👉 **Observe:** quantas compras passaram e quantas foram barradas. Quanto tempo a barrada esperou?

Pergunta: *"recusar gente na porta parece pior do que deixar todo mundo entrar. Por que pode ser melhor para quem está dentro? E para quem foi barrado?"*

Pergunta: *"por que o limite é de compras em andamento, e não de compras por segundo? O que aconteceria com um limite por segundo se o gateway ficasse mais lento?"*

Experimente outros limites e rode a estreia de novo:

```bash
MAX_COMPRAS_SIMULTANEAS=10 docker compose up -d nginx      # porta estreita
MAX_COMPRAS_SIMULTANEAS=1000 docker compose up -d nginx    # porta aberta, como se não houvesse limite
docker compose run --rm --service-ports k6 run /scripts/estreia.js
docker compose up -d nginx                                  # volta ao padrão
```

👉 **Observe:** os barrados na porta, o tempo da compra e quantos compradores conseguiram comprar no pico.

Pergunta: *"qual é o limite certo? O que acontece se ele for estreito demais? E largo demais?"*

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou. Elas guiam as próximas aulas:

- O que limita o Ingressa agora?
- Do que a compra gasta, o que precisa mesmo ser feito na hora?
- Quem foi barrado na porta: o que um site de verdade faria com essa pessoa?

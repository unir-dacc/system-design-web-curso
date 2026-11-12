# Aula 05: Fila com worker

> **Objetivo:** mostrar que nem todo trabalho precisa ser feito enquanto o
> usuário espera, e que uma fila deixa o Ingressa aceitar compras rápido e
> concluí-las no ritmo que ele aguenta, sem perder nenhuma.

```
                                        ┌──────────────────────┐
            ┌──────────────┐        ┌──▶│ Ingressa (backend 1) │──┐  reserva o assento
 usuário ──▶│    Nginx     │────────┤   └──────────────────────┘  │  e põe a compra na fila
            │ rate limit   │        │   ┌──────────────────────┐  │
            └──────────────┘        └──▶│ Ingressa (backend 2) │──┤
                                        └──────────────────────┘  ▼
                                                           ┌────────────┐
                                                           │   Redis    │  fila de compras
                                                           └─────┬──────┘
                                                                 ▼
                                        ┌──────────────────────────────┐
                                        │ Worker: cobra, confirma,     │──▶ gateway, cinema,
                                        │ emite os ingressos, e-mail   │    Mailpit
                                        └──────────────────────────────┘
```

O orçamento é o mesmo: 2 CPUs e 2 GB. O worker não ganhou hardware novo: os backends cederam uma parte do deles.

**[🖊️ Abrir o diagrama desta etapa no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/05-fila/arquitetura.excalidraw)**,
para desenhar por cima durante a aula. A peça nova da etapa está em amarelo.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`05-fila/`).

```bash
docker compose down -v          # garante que começa do zero
docker compose up -d --build --wait
```

Rode a estreia das etapas anteriores antes da aula: o relatório desta etapa compara com o último resultado delas.

---

## 1. Onde a 04 parou

Abra `../04-rate-limit/relatorios/estreia.html`, na velocidade de cada endpoint.

Pergunta para a turma: *"qual endpoint é o mais lento? O que ele faz enquanto o usuário espera?"*

Abra `realizar_compra` em `../04-rate-limit/app/compra.py` e liste os passos.

Pergunta: *"de todos esses passos, quais o usuário precisa esperar para saber que a compra foi aceita?"*

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `app/compra.py` | A compra foi dividida em duas: `realizar_compra` (a requisição) e `concluir_compra` (o worker) |
| `app/fila.py` | A fila no Redis. O que é a lista "processando" e por que ela existe? |
| `app/worker.py` | O worker: pega uma tarefa, conclui a compra, apaga a tarefa |
| `app/routes/pedidos.py` | `POST /pedidos` responde **202** (aceito, ainda processando). O usuário não espera o resto |
| `app/notificacoes.py` | O e-mail é a única forma de o usuário saber o resultado: ingressos ou "não deu certo" |
| `docker-compose.yml` | O worker entrou, e o orçamento foi dividido de novo. E o Redis agora grava em disco: por quê? |

Pergunta: *"se o worker fizer a mesma compra duas vezes, o cliente é cobrado duas vezes? O que impede?"*

## 3. Uma compra agora

```bash
curl -s -X POST localhost:8000/admin/reset > /dev/null
curl -s -X POST localhost:8000/pedidos -H 'Content-Type: application/json' -d '{
  "sessao_id": 1, "nome": "Maria", "cpf": "529.982.247-25", "email": "maria@exemplo.com",
  "cartao_token": "tok_aprovado",
  "itens": [{"assento": "A1"}, {"assento": "A2", "tipo": "meia"}]
}' -w '\n⏱  %{time_total}s\n'

curl -s localhost:8000/pedidos/1; echo       # repita algumas vezes
docker compose logs worker | tail -5
```

👉 **Observe:** o tempo da resposta e o status do pedido logo depois. Abra o Mailpit (http://localhost:8025): o e-mail chegou quando?

Pergunta: *"o usuário saiu do site achando que comprou. E se o cartão for recusado depois?"*

Repita com `"cartao_token": "tok_recusado"` e veja o e-mail e o assento no mapa.

## 4. A fila segurando o pico

Deixe a fila crescer: pare o worker, faça algumas compras e veja a fila.

```bash
docker compose stop worker
for i in $(seq 5); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/pedidos -H 'Content-Type: application/json' \
    -d "{\"sessao_id\":7,\"nome\":\"Maria\",\"cpf\":\"39053344705\",\"email\":\"m@ex.com\",\"cartao_token\":\"tok_aprovado\",\"itens\":[{\"assento\":\"D$i\"}]}"
done
docker compose exec redis redis-cli llen fila:compras
curl -s localhost:8000/sessoes/7/assentos | grep -o '{"codigo":"D1","status":"[a-z]*"}'

docker compose start worker
sleep 5
docker compose exec redis redis-cli llen fila:compras
docker compose logs worker | tail -5
```

👉 **Observe:** o que o usuário recebeu com o worker parado, o tamanho da fila, o assento D1, e o que acontece quando o worker volta.

Pergunta: *"o worker caiu e ninguém perdeu a compra. E se fosse o Redis que caísse?"*

## 5. A estreia

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

Durante o pico, acompanhe a fila:

```bash
watch -n1 docker compose exec redis redis-cli llen fila:compras
```

| Bloco | Perguntas |
|-------|-----------|
| A progressão das vendas | As vendas acompanham a procura até onde? E depois? |
| O ganho de cada etapa | O que mudou em relação à 04? |
| A velocidade de cada endpoint | Como ficou o `POST /pedidos`? |
| O pico: o sistema | Até quanto a fila de compras cresceu? Quantas compras ainda faltavam no fim, e em quanto tempo o worker termina? |

👉 **Observe também:** no `docker compose stats`, a CPU dos backends e do worker. Quem está no limite agora?

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

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

- O que limita o Ingressa agora: os backends ou o worker?
- E se a fila crescer mais rápido do que o worker consegue esvaziar?
- Quanto tempo depois da compra o usuário recebe o e-mail? Quanto ele aceitaria esperar?

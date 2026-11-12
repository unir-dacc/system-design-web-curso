# Aula 01: O Monolito

> **Objetivo:** apresentar o Ingressa funcionando e colocá-lo à prova na
> estreia do maior filme da história.

```
            ┌──────────────────────────┐        ┌───────────────────────┐
 usuário ──▶│  Ingressa (1 processo)   │──────▶ │ Sistema do cinema     │
            │  FastAPI síncrono        │        └───────────────────────┘
            │  1 CPU / 512 MB          │──────▶ ┌───────────────────────┐
            └────────────┬─────────────┘        │ Gateway de pagamento  │
                         │                      └───────────────────────┘
                   ┌─────▼─────┐                ┌───────────────────────┐
                   │ Postgres  │                │ Mailpit (SMTP falso)  │
                   └───────────┘                └───────────────────────┘
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`01-monolito/`).

```bash
docker compose down -v          # garante que começa do zero
docker compose up -d --build --wait
```

Deixe abertas três abas: http://localhost:8000/docs, http://localhost:8025 (e-mails) e um terminal com `docker compose stats`.

### Sobre o teste de carga

Existe **um único teste**: `estreia.js`, a abertura das vendas do maior filme da história.
Primeiro o público cresce aos poucos, para descobrir até quantos usuários o Ingressa aguenta. Depois vem o pico:
usuários chegando aos montes, usuários muito engajados (nunca desistem) e robôs cambistas, tudo ao mesmo tempo.
Como numa loja de verdade, a maioria dos usuários só olha: abre a programação, olha o mapa de uma ou duas sessões e vai embora.
De cada 10, 3 compram.

- **Durante:** painel em tempo real em **http://localhost:5665**.
- **Depois:** abra **`relatorios/estreia.html`** no navegador e projete para a turma
  (`xdg-open relatorios/estreia.html`). Um resumo também aparece no terminal.
  Gráficos ao longo do minuto: `relatorios/ultimo-teste.html`.
- **Cada rodada começa do zero** (a configuração dos simuladores é mantida).
- Se nada aparecer na tela, veja `relatorios/k6.log`.

---

## 1. Tour pelo código

Siga o caminho de uma compra, nesta ordem:

| Arquivo | O que mostrar |
|---------|---------------|
| `app/main.py` | Ponto de entrada; tabelas e catálogo criados no startup |
| `app/models.py` | Filme, Sessão, Pedido, Ingresso. **Os assentos não estão aqui**: quem manda neles é o cinema |
| `app/routes/pedidos.py` | Como cada erro de negócio vira um status HTTP (402, 409, 422) |
| `app/compra.py` | O coração da aula: os passos de uma compra, e como as regras de negócio são garantidas |
| `app/clients.py` | Como o Ingressa conversa com os sistemas externos |
| `../shared/sistema-cinema/app.py` | O sistema legado da rede de cinemas |

Pergunta para a turma: *"quanto tempo vocês acham que uma compra leva?"*

## 2. Uma compra de verdade

```bash
curl -s -X POST localhost:8000/pedidos -H 'Content-Type: application/json' -d '{
  "sessao_id": 1, "nome": "Maria", "cpf": "529.982.247-25", "email": "maria@exemplo.com",
  "cartao_token": "tok_aprovado",
  "itens": [{"assento": "A1"}, {"assento": "A2", "tipo": "meia"}]
}' -w '\n⏱  %{time_total}s\n'
```

👉 **Observe:** o tempo da compra, o preço da meia-entrada e a taxa de conveniência.
Abra o Mailpit e veja o e-mail com os QR codes.

Mostre os erros de negócio:

```bash
# mesmo assento de novo
# cartao_token "tok_recusado"
# cpf "123.456.789-00"
```

Pergunta: *"quem impediu a venda do mesmo assento duas vezes: o Ingressa ou o cinema?"*

## 3. Para onde foi o tempo?

Peça para a turma descobrir onde a compra passou o tempo. As pistas estão na configuração dos sistemas externos:

```bash
curl -s localhost:8001/admin/config; echo     # gateway de pagamento
curl -s localhost:8002/admin/config; echo     # sistema do cinema
```

Volte para `app/compra.py` e some, passo a passo.

Pergunta: *"de todo esse tempo, quanto o Ingressa passou trabalhando de verdade?"*

## 4. A estreia

A rodada tem duas partes e leva alguns minutos:

1. **A subida:** o público cresce aos poucos (4 usuários por segundo, 8, 12, 16...). Em cada degrau, o teste confere se o site continua viável.
2. **O pico:** as vendas abrem de vez, com usuários, usuários muito engajados e robôs cambistas ao mesmo tempo.

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

Leia o relatório com a turma, bloco por bloco:

| Bloco | Perguntas |
|-------|-----------|
| Topo | Até quantos usuários por segundo o Ingressa aguenta? No pico, os curiosos conseguiram ver o que queriam? E os compradores, conseguiram comprar? Apareceu algum alerta? |
| A subida | Em qual degrau a linha fica vermelha? O que acontece com as "pessoas no site ao mesmo tempo" depois desse ponto? |
| O ganho de cada etapa | Por enquanto só tem uma linha. O que esperamos ver nela nas próximas aulas? |
| O pico: o sistema | Compare as requisições enviadas com as respondidas. Quantos usuários esperavam ao mesmo tempo? |
| O pico: cada público | Em qual página cada público se perdeu? Quem sofreu mais: quem só queria olhar ou quem queria comprar? |
| O pico: os engajados | Quem nunca desiste conseguiu comprar? |
| A espera e as metas | Quanto tempo o usuário esperou? Quais metas passaram? |

👉 **Observe também:** no `docker compose stats`, CPU e memória do Ingressa durante o teste.
Depois que o teste acaba, o Ingressa ainda responde?

```bash
curl -s -m 5 localhost:8000/health; echo
docker compose restart ingressa        # se precisar destravar
```

Pergunta: *"quantas pessoas a estreia do maior filme da história vai trazer? E quantas o Ingressa aguenta?"*

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

Pergunta: *"se a gente der 4 CPUs para o Ingressa, melhora?"*

## 5. O cambista e as compras simultâneas

Um cambista dispara 20 compras ao mesmo tempo com o mesmo CPF (o limite é 6 por sessão):

```bash
curl -s -X POST localhost:8000/admin/reset > /dev/null
for i in $(seq 20); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/pedidos -H 'Content-Type: application/json' \
    -d "{\"sessao_id\":2,\"nome\":\"Cambista\",\"cpf\":\"52998224725\",\"email\":\"c@ex.com\",\"cartao_token\":\"tok_aprovado\",\"itens\":[{\"assento\":\"A$i\"}]}" &
done | sort | uniq -c
curl -s localhost:8000/sessoes/2/resumo; echo
```

👉 **Observe:** quantas compras deram 201 e quantas deram 422, e o `maior_compra_por_cpf` no resumo.

Pergunta: *"se as 20 compras chegam no mesmo instante e todas conferem o limite antes de gravar, por que elas não passam todas?"*

Abra `registrar_pedido` em `app/compra.py`: a trava no banco (`pg_advisory_xact_lock`) e o pedido registrado **antes** das chamadas lentas.

Pergunta: *"por que a trava fica no banco e não numa variável do Python? E por que ela é solta antes de falar com o cinema?"*

## 6. Quando um sistema externo fica lento

```bash
# gateway lento (também dá para fazer pelo Swagger: http://localhost:8001/docs)
curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"latencia_ms": 8000}'

docker compose run --rm --service-ports k6 run -e USUARIOS=3 /scripts/estreia.js

# volta ao normal
curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"latencia_ms": 1200}'
```

Experimente também `{"taxa_travamento": 0.2}`: algumas cobranças nunca respondem. E `{"taxa_erro": 0.3}`: o gateway responde com erro.

👉 **Observe:** o que acontece com o assento e com o pedido de uma compra cujo pagamento falhou (mapa da sessão e `GET /pedidos/{id}`).

Pergunta: *"um sistema que não é nosso pode derrubar o nosso?"*

Abra `cobrar` em `app/clients.py`.

Pergunta: *"se o gateway não respondeu, o cliente foi cobrado ou não? Por que não dá para simplesmente liberar o assento?"*

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

- O que limitou o Ingressa na estreia?
- O que acontece com quem desiste no meio da compra?
- Como descobrir onde está a lentidão sem ler o código?

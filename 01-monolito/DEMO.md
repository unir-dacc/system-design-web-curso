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
Fãs chegando aos montes e robôs cambistas, tudo ao mesmo tempo, por 1 minuto.

- **Durante:** painel em tempo real em **http://localhost:5665**.
- **Depois:** o resumo aparece no terminal e fica salvo em `relatorios/estreia.txt`.
  O painel completo fica em `relatorios/ultimo-teste.html`.
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
| `app/compra.py` | O coração da aula: os 5 passos de uma compra |
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

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
```

Leia o resumo com a turma, bloco por bloco:

| Bloco | Perguntas |
|-------|-----------|
| 1. A carga | Quantos fãs apareceram? Quantos estavam esperando ao mesmo tempo? |
| 2. O que o Ingressa conseguiu atender | Compare as requisições enviadas com as respondidas. Compare os ingressos vendidos com os que o fã viu confirmados: o que aconteceu com a diferença? |
| 3. O que o fã sentiu | Quanto tempo o fã esperou? Quantos desistiram? Quantos nem conseguiram entrar? |
| 4. Metas | Quais passaram? |

👉 **Observe também:** no `docker compose stats`, CPU e memória do Ingressa durante o teste.
Depois que o teste acaba, o Ingressa ainda responde?

```bash
curl -s -m 5 localhost:8000/health; echo
docker compose restart ingressa        # se precisar destravar
```

Pergunta: *"se a gente der 4 CPUs para o Ingressa, melhora?"*

## 5. Com pouca gente

Rode a mesma estreia com bem menos fãs:

```bash
docker compose run --rm --service-ports k6 run -e FAS=3 /scripts/estreia.js
```

👉 **Observe:** as metas de regra de negócio (limite por CPF e cota de meia-entrada).

Volte para `app/compra.py` e procure o momento em que as regras são verificadas e o momento em que os ingressos são gravados.

Pergunta: *"por que testar com 1 usuário nunca pegaria isso?"*

## 6. Quando um sistema externo fica lento

```bash
# gateway lento (também dá para fazer pelo Swagger: http://localhost:8001/docs)
curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"latencia_ms": 8000}'

docker compose run --rm --service-ports k6 run -e FAS=3 /scripts/estreia.js

# volta ao normal
curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"latencia_ms": 1200}'
```

Experimente também `{"taxa_travamento": 0.2}`: algumas cobranças nunca respondem.

Pergunta: *"um sistema que não é nosso pode derrubar o nosso?"*

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou. Elas guiam as próximas aulas:

- O que limitou o Ingressa na estreia?
- Por que as regras de negócio falharam?
- O que acontece com quem desiste no meio da compra?
- Como descobrir onde está a lentidão sem ler o código?

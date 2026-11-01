# Aula 01: O Monolito

> **Objetivo:** apresentar o Ingressa funcionando e mostrar que "funciona"
> não quer dizer "aguenta". Cada ⚠️ no código vira uma aula futura.

```
            ┌──────────────────────────┐        ┌───────────────────────┐
 usuário ──▶│  Ingressa (1 processo)   │──────▶ │ Sistema do cinema     │ lento, 10 req simultâneas
            │  FastAPI síncrono        │        └───────────────────────┘
            │  1 CPU / 512 MB          │──────▶ ┌───────────────────────┐
            └────────────┬─────────────┘        │ Gateway de pagamento  │ ~1,2s por cobrança
                         │                      └───────────────────────┘
                   ┌─────▼─────┐                ┌───────────────────────┐
                   │ Postgres  │                │ Mailpit (SMTP falso)  │
                   └───────────┘                └───────────────────────┘
```

## 0. Preparação (antes da aula)

```bash
make up STEP=01
```

Deixe abertas três abas: http://localhost:8000/docs, http://localhost:8025 (e-mails) e um terminal com `make stats`.

---

## 1. Tour pelo código (~10 min)

Siga o caminho de uma compra, nesta ordem:

| Arquivo | O que mostrar |
|---------|---------------|
| `app/main.py` | Ponto de entrada; tabelas e catálogo criados no startup |
| `app/models.py` | Filme, Sessão, Pedido, Ingresso. **Os assentos não estão aqui**: quem manda neles é o cinema |
| `app/routes/pedidos.py` | Como cada erro de negócio vira um status HTTP (402, 409, 422) |
| `app/compra.py` | **O coração da aula.** Os 5 passos da compra e os ⚠️ |
| `app/clients.py` | Chamadas aos sistemas externos, **sem timeout** |
| `../shared/sistema-cinema/app.py` | O "sistema legado": lento e com fila |

Pergunta para a turma: *"quanto tempo vocês acham que uma compra leva?"*

## 2. Uma compra de verdade (~5 min)

```bash
curl -s -X POST localhost:8000/pedidos -H 'Content-Type: application/json' -d '{
  "sessao_id": 1, "nome": "Maria", "cpf": "529.982.247-25", "email": "maria@exemplo.com",
  "cartao_token": "tok_aprovado",
  "itens": [{"assento": "A1"}, {"assento": "A2", "tipo": "meia"}]
}' -w '\n⏱  %{time_total}s\n'
```

👉 **Mostre:** ~2,2s para UMA compra; total com meia-entrada e taxa de 10%.
Abra o Mailpit: e-mail com os QR codes.

Mostre os erros de negócio:

```bash
# mesmo assento de novo -> 409
# cartao_token "tok_recusado" -> 402
# cpf "123.456.789-00" -> 422
```

👉 **Mostre:** o 409 vem do sistema do cinema, que é quem garante que o assento não é vendido duas vezes.

## 3. Onde estão os 2 segundos? (~5 min)

| Passo | Quem | Tempo |
|-------|------|-------|
| Reservar assentos | cinema | ~600 ms |
| Cobrar | gateway | ~1200 ms |
| Confirmar | cinema | ~400 ms |
| Gravar + QR code + e-mail | Ingressa | ~50 ms |

👉 **Ponto-chave:** o Ingressa passa **mais de 95% do tempo esperando** outros sistemas. Guarde isso para a aula de async (00) e de filas (05).

## 4. Navegação: o custo de ler (~5 min)

```bash
make load SCRIPT=navegacao
```

👉 **Mostre:** consultas ao banco em **~7 ms**, mapa de assentos com p95 **~3,3 s**.
O mapa vem do cinema a cada visita, e o cinema atende 10 por vez. Motivação da aula de **cache (04)**.

## 5. Abertura das vendas (~10 min)

Num terminal deixe `make estado` e `make stats`; no outro:

```bash
make load SCRIPT=abertura-vendas
```

Resultado esperado (100 usuários, 1 min):

| Métrica | Valor aproximado |
|---------|------------------|
| Compras confirmadas | ~325 (≈ 4,6 por segundo) |
| p95 da compra | **~11 s** |
| Erros | 0 |

👉 **Mostre:** nada quebrou, mas ninguém espera 11 s para comprar um ingresso.
No `make stats`, a CPU do Ingressa está **baixa**: o gargalo não é o hardware, é a **espera**.
No `make estado`, veja a fila do cinema.

Pergunta: *"se a gente der 4 CPUs para o Ingressa, melhora?"* (spoiler: quase nada; aulas 00 e 02).

## 6. Os bugs escondidos (~10 min)

### Limite de 6 ingressos por CPF

```bash
make up STEP=01
make load SCRIPT=corrida-limite-cpf
```

👉 **Mostre:** `✗ compras_confirmadas: 20`. Um único CPF comprou **20 ingressos** com limite de 6.

### Cota de meia-entrada (40% = 38 lugares na sala 3)

```bash
make load SCRIPT=corrida-meia-entrada
```

👉 **Mostre:** `✗ meias_confirmadas: 60` com cota de **38**. Isso é problema legal, não só técnico.

Volte para `app/compra.py` e leia o comentário ⚠️ do *check-then-act*.
Pergunta: *"por que o teste com 1 usuário nunca pegaria isso?"*. Resolvido na aula de **banco de dados (03)**.

## 7. Quando um sistema externo quebra (~5 min)

```bash
make gateway CONFIG='{"latencia_ms": 8000}'      # gateway lento
make load SCRIPT=abertura-vendas VUS=50
make gateway CONFIG='{"latencia_ms": 1200}'      # volta ao normal
```

👉 **Mostre:** um sistema que não é nosso deixa o Ingressa inteiro lento, porque cada compra segura uma das 40 threads.
E com `{"taxa_travamento": 0.2}`, requisições ficam presas **para sempre** (sem timeout). Aula de **resiliência (07)**.

---

## Resumo para o quadro

| Problema observado | Aula |
|--------------------|------|
| Compra demora segundos esperando outros sistemas | 00 async, 05 filas |
| Um único processo | 02 load balancer |
| CPF e meia-entrada furam o limite | 03 banco de dados |
| N+1 consultas, sem índices | 03 banco de dados |
| Mapa de assentos lento a cada visita | 04 cache |
| QR code e e-mail dentro da requisição | 05 filas |
| Sem timeout, reserva presa se o gateway falhar | 07 resiliência |
| "Está lento, mas onde?" | 08 observabilidade |

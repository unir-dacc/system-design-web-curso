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

👉 **Ponto-chave:** o Ingressa passa **mais de 95% do tempo esperando** outros sistemas. Guarde isso para as aulas de async (02) e de filas (06).

## 4. A estreia: o pico do pico (~10 min)

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
```

Resultado medido (50 fãs/s + 20 robôs cambistas, 1 minuto):

```
  PÚBLICO
    Fãs que tentaram comprar ........ 1761
    Não conseguiram nem entrar ...... 988
    Desistiram (mais de 30 s) ....... 1801

  VENDAS
    Ingressos vendidos .............. 52 de 4800
    ...e o fã viu a confirmação ..... 0

  METAS
    ❌ Mapa abre em até 2 s para 95% dos fãs
    ❌ Compra em até 3 s para 95% dos fãs
    ❌ Menos de 1% de erros ................. erros: 97.0%
    ⚠️  o Ingressa TRAVOU e não respondeu nem depois que o público foi embora.
```

👉 **Mostre:**
- **52 ingressos vendidos de 4800**, e nenhum fã viu a confirmação. Os 52 foram vendidos (e cobrados!) para quem já tinha desistido.
- No painel, a duração das requisições cola em 30 s: é o tempo da paciência do fã.
- No `docker compose stats`, a **memória** do Ingressa encostada nos 512 MB: milhares de pedidos acumulados.
- O Ingressa **não volta sozinho**. O servidor continua trabalhando para quem já foi embora.

```bash
docker compose restart ingressa        # para destravar
```

Pergunta: *"se a gente der 4 CPUs para o Ingressa, melhora?"* (spoiler: quase nada; aulas 02 e 03).

## 5. Os bugs escondidos (~10 min)

No pico não dá nem para ver os bugs, porque nada funciona. Com pouca gente, o sistema responde e eles aparecem:

```bash
docker compose run --rm --service-ports k6 run -e FAS=3 /scripts/estreia.js
```

```
  METAS
    ❌ Máximo de 6 ingressos por CPF ........... maior compra: 16
```

👉 **Mostre:** os robôs cambistas compraram **16 ingressos com o mesmo CPF**, com limite de 6.
Volte para `app/compra.py` e leia o comentário ⚠️ do *check-then-act*.
Pergunta: *"por que testar com 1 usuário nunca pegaria isso?"*. Resolvido na aula de **banco de dados (04)**.

## 6. Quando um sistema externo quebra (~5 min)

```bash
# gateway lento (também dá para fazer pelo Swagger: http://localhost:8001/docs)
curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"latencia_ms": 8000}'

docker compose run --rm --service-ports k6 run -e FAS=3 /scripts/estreia.js

# volta ao normal
curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"latencia_ms": 1200}'
```

👉 **Mostre:** um sistema que não é nosso deixa o Ingressa inteiro lento, porque cada compra segura uma das 40 threads.
E com `{"taxa_travamento": 0.2}`, requisições ficam presas **para sempre** (sem timeout). Aula de **resiliência (08)**.

---

## Resumo para o quadro

| Problema observado | Aula |
|--------------------|------|
| Compra demora segundos esperando outros sistemas | 02 async, 06 filas |
| Um único processo | 03 load balancer |
| Cambistas furam o limite por CPF | 04 banco de dados |
| N+1 consultas, sem índices | 04 banco de dados |
| Mapa de assentos lento a cada visita | 05 cache |
| QR code e e-mail dentro da requisição | 06 filas |
| Sem timeout, reserva presa se o gateway falhar | 08 resiliência |
| "Está lento, mas onde?" | 09 observabilidade |

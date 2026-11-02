# Aula 03: Async

> **Objetivo:** mostrar por que o Ingressa da 01 travava esperando, e o que muda
> quando esperar deixa de ocupar uma thread.

```
            ┌──────────────────────────┐        ┌───────────────────────┐
 usuário ──▶│  Ingressa (1 processo)   │──────▶ │ Sistema do cinema     │
            │  FastAPI async           │        └───────────────────────┘
            │  1 CPU / 512 MB          │        ┌───────────────────────┐
            │  ┌────────────────────┐  │──────▶ │ Gateway de pagamento  │
            │  │ pagamento em       │  │        └───────────────────────┘
            │  │ segundo plano      │  │        ┌───────────────────────┐
            │  └────────────────────┘  │──────▶ │ Mailpit (SMTP falso)  │
            └────────────┬─────────────┘        └───────────────────────┘
                   ┌─────▼─────┐
                   │ Postgres  │
                   └───────────┘
```

O hardware é o mesmo da etapa 01. O que muda é só o código do Ingressa.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`03-async/`).

```bash
docker compose down -v          # garante que começa do zero
docker compose up -d --build --wait
```

Tenha em mãos o relatório da etapa 01 (`../01-monolito/relatorios/estreia.html`) para comparar.

---

## 1. O que mudou no código

| Arquivo | O que mostrar |
|---------|---------------|
| `app/routes/catalogo.py` | As rotas viraram `async def`. Compare com a 01: não existe mais o pool de 40 threads |
| `app/clients.py` | Cada chamada a um sistema externo agora tem `await` |
| `app/compra.py` | A compra foi dividida em duas partes: a requisição e o segundo plano |
| `app/routes/pedidos.py` | `POST /pedidos` responde **202** em vez de 201 |
| `app/db.py` e `app/models.py` | O banco também virou async; por que `lazy="selectin"`? |

Pergunta para a turma: *"o que o `await` faz enquanto o gateway não responde?"*

Em `concluir_compra`, mostre o `await db.commit()` antes da cobrança.

Pergunta: *"por que devolver a conexão do banco antes de esperar o gateway? O que aconteceria se ela ficasse presa?"*

## 2. Uma compra agora

```bash
curl -s -X POST localhost:8000/pedidos -H 'Content-Type: application/json' -d '{
  "sessao_id": 1, "nome": "Maria", "cpf": "529.982.247-25", "email": "maria@exemplo.com",
  "cartao_token": "tok_aprovado",
  "itens": [{"assento": "A1"}, {"assento": "A2", "tipo": "meia"}]
}' -w '\n⏱  %{time_total}s\n'

curl -s localhost:8000/pedidos/1; echo       # repita algumas vezes
```

👉 **Observe:** o tempo da resposta, o status do pedido logo depois de comprar, e como ele muda nas consultas seguintes.

Pergunta: *"a compra ficou mais rápida, ou só a resposta? O que o usuário vê na tela enquanto isso?"*

## 3. A estreia

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

Abra o relatório da etapa 01 ao lado e compare, bloco por bloco:

| Bloco | Perguntas |
|-------|-----------|
| Topo | Até quantos usuários por segundo cada etapa aguenta? Apareceu algum alerta? |
| A subida | Em qual degrau a linha fica vermelha agora? O que piora primeiro: o mapa ou a compra? |
| O pico | Quantos usuários conseguiram comprar? O Ingressa respondeu o que recebeu? |
| A espera e as metas | Quais metas passaram agora e não passavam antes? |

👉 **Observe também:** no `docker compose stats`, CPU do Ingressa, do Postgres e do sistema do cinema. Quem está trabalhando mais?
Depois que o teste acaba, o Ingressa ainda responde?

```bash
curl -s -m 5 localhost:8000/health; echo
```

Pergunta: *"na 01, o limite era o número de threads esperando. E agora, o que segura o Ingressa?"*

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

## 4. Quando o pagamento falha em segundo plano

O usuário já recebeu a resposta. E se o gateway falhar depois?

```bash
curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"taxa_erro": 1}'

curl -s -X POST localhost:8000/pedidos -H 'Content-Type: application/json' -d '{
  "sessao_id": 1, "nome": "Maria", "cpf": "390.533.447-05", "email": "maria@exemplo.com",
  "cartao_token": "tok_aprovado", "itens": [{"assento": "B1"}]
}'; echo

curl -s localhost:8000/pedidos/2; echo        # repita algumas vezes

curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"taxa_erro": 0}'
```

👉 **Observe:** o status do pedido e o assento B1 no mapa da sessão 1.

Pergunta: *"quem avisa o usuário que deu errado, se a requisição dele já terminou?"*

## 5. E se o Ingressa cair no meio de um pagamento?

```bash
curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"latencia_ms": 10000}'

curl -s -X POST localhost:8000/pedidos -H 'Content-Type: application/json' -d '{
  "sessao_id": 1, "nome": "Maria", "cpf": "111.444.777-35", "email": "maria@exemplo.com",
  "cartao_token": "tok_aprovado", "itens": [{"assento": "C1"}]
}'; echo
docker compose restart ingressa               # logo em seguida, antes do pagamento terminar

curl -s localhost:8000/pedidos/3; echo        # espere alguns segundos e repita

curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"latencia_ms": 1200}'
```

👉 **Observe:** o status do pedido depois que o Ingressa volta, e o assento C1 no mapa.

Abra `realizar_compra` em `app/compra.py` e leia o ⚠️ sobre `asyncio.create_task`.

Pergunta: *"onde estava guardado o \"pagamento em andamento\"? O que seria preciso para ele sobreviver a uma queda?"*

## 6. O cambista continua barrado?

```bash
curl -s -X POST localhost:8000/admin/reset > /dev/null
for i in $(seq 20); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/pedidos -H 'Content-Type: application/json' \
    -d "{\"sessao_id\":2,\"nome\":\"Cambista\",\"cpf\":\"52998224725\",\"email\":\"c@ex.com\",\"cartao_token\":\"tok_aprovado\",\"itens\":[{\"assento\":\"A$i\"}]}" &
done | sort | uniq -c
sleep 3
curl -s localhost:8000/sessoes/2/resumo; echo
```

👉 **Observe:** os códigos de resposta e o `maior_compra_por_cpf`.

Pergunta: *"com o async, várias compras rodam \"ao mesmo tempo\" no mesmo processo. A trava no banco ainda é necessária?"*

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou. Elas guiam as próximas aulas:

- O que limitou o Ingressa na estreia desta vez?
- Quantas vezes o Ingressa pergunta a mesma coisa ao sistema do cinema?
- O que se perde quando o processo cai?

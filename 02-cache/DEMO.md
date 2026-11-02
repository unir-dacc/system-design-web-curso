# Aula 02: Cache do mapa de assentos

> **Objetivo:** descobrir quem limitava o Ingressa na aula 01 e aliviar esse
> ponto com um cache, sem mudar o hardware do Ingressa.

```
            ┌──────────────────────────┐   só quando o cache   ┌───────────────────────┐
 usuário ──▶│  Ingressa (1 processo)   │──── não tem o mapa ──▶│ Sistema do cinema     │
            │  1 CPU / 512 MB          │                       └───────────────────────┘
            └──────┬─────────────┬─────┘──────────────────────▶┌───────────────────────┐
                   │             │                             │ Gateway de pagamento  │
             ┌─────▼─────┐ ┌─────▼─────┐                       └───────────────────────┘
             │ Postgres  │ │   Redis   │ ◀── novo: guarda o mapa de cada sessão por alguns segundos
             └───────────┘ └───────────┘
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`02-cache/`).

```bash
(cd ../01-monolito && docker compose down -v)   # derruba a etapa anterior
docker compose down -v
docker compose up -d --build --wait
```

Deixe à mão o relatório da aula 01 (`../01-monolito/relatorios/estreia.html`) para comparar.

---

## 1. Quem limitava o Ingressa?

Volte ao relatório da aula 01 e à configuração dos sistemas externos:

```bash
curl -s localhost:8002/admin/config; echo     # sistema do cinema
curl -s localhost:8001/admin/config; echo     # gateway de pagamento
```

Pergunta para a turma: *"cada usuário que abre o mapa e compra ocupa o sistema do cinema por quanto tempo?
E o cinema atende quantos ao mesmo tempo? Então, quantos usuários por segundo ele aguenta?"*

Compare a conta com o número do topo do relatório da 01.

Pergunta: *"de todo o tempo que o cinema gasta com um usuário, qual parte é só para mostrar o mapa?"*

## 2. O que mudou no código

```bash
git diff --no-index ../01-monolito/app app
git diff --no-index ../01-monolito/docker-compose.yml docker-compose.yml
```

| Arquivo | O que mostrar |
|---------|---------------|
| `app/cache.py` | Procura o mapa no Redis. Se a cópia venceu, **só uma requisição** vai ao cinema buscar outra (trava no Redis) e as demais recebem a cópia anterior |
| `app/assentos.py` | O Ingressa guarda no Redis os assentos que ele mesmo travou e vendeu. Antes de pedir uma reserva ao cinema, a compra trava os assentos aqui: tudo ou nada |
| `app/compra.py` | O passo novo: travar os assentos no Ingressa antes de chamar o cinema |
| `app/routes/catalogo.py` | O mapa: a cópia do cinema combinada com as travas e vendas do Ingressa |
| `app/routes/admin.py` | O reset do teste também limpa o Redis |
| `docker-compose.yml` | O Redis entrou, com seu próprio limite de CPU e memória |

Pergunta: *"o Redis não grava nada em disco. Se ele reiniciar no meio da estreia, algum assento pode ser vendido duas vezes? E o limite por CPF?"*

## 3. O cache funcionando

Abra o mapa da mesma sessão algumas vezes seguidas:

```bash
for i in 1 2 3; do curl -s -o /dev/null -w '⏱  %{time_total}s\n' localhost:8000/sessoes/1/assentos; done
```

👉 **Observe:** o tempo da primeira vez e das seguintes.

Espie dentro do Redis:

```bash
docker compose exec redis redis-cli KEYS 'mapa:*'
docker compose exec redis redis-cli GET mapa:1 | head -c 80; echo   # a cópia e a hora em que foi buscada
docker compose exec redis redis-cli INFO stats | grep keyspace
```

Pergunta: *"o que significam `keyspace_hits` e `keyspace_misses`?"*

Pergunta: *"quando a cópia de uma sessão vence e 100 pessoas abrem o mapa no mesmo instante, quantas vezes o cinema é chamado? Procure a resposta em `app/cache.py`."*

## 4. A estreia

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

Abra o relatório desta aula ao lado do relatório da aula 01.

| Bloco | Perguntas |
|-------|-----------|
| Topo | O máximo que o Ingressa aguenta mudou? Bate com a conta da seção 1? |
| A subida | Em qual degrau a linha fica vermelha agora? |
| O pico | O pico ainda derruba o Ingressa? Por quê? |

Depois do teste, veja quantas vezes o cache evitou ir ao cinema:

```bash
docker compose exec redis redis-cli INFO stats | grep keyspace
```

## 5. O preço do cache

As compras feitas pelo Ingressa aparecem no mapa na hora. Mas o cinema também vende na bilheteria, e isso o Ingressa só fica sabendo quando a cópia do mapa é renovada. Use a sessão 3, que o teste de carga não usa:

```bash
# 1. guarda a cópia do mapa
curl -s localhost:8000/sessoes/3/assentos | grep -o '"codigo":"J15","status":"[a-z]*"'

# 2. a bilheteria do cinema reserva o J15 direto no sistema do cinema
curl -s -X POST localhost:8002/sessoes/3/reservas -H 'Content-Type: application/json' -d '{"assentos": ["J15"]}' -o /dev/null -w 'bilheteria: %{http_code}\n'

# 3. o mapa do Ingressa ainda não sabe
curl -s localhost:8000/sessoes/3/assentos | grep -o '"codigo":"J15","status":"[a-z]*"'

# 4. um usuário tenta comprar o J15 pelo Ingressa
curl -s -X POST localhost:8000/pedidos -H 'Content-Type: application/json' -d '{
  "sessao_id": 3, "nome": "Maria", "cpf": "529.982.247-25", "email": "maria@exemplo.com",
  "cartao_token": "tok_aprovado", "itens": [{"assento": "J15"}]
}' -w '\ncompra: %{http_code}\n'
```

👉 **Observe:** o status do J15 no mapa do Ingressa e a resposta da compra. (Se o J15 já tiver sido usado numa demonstração anterior, use outro assento, como J14.)

Pergunta: *"quem impediu a venda dupla, se o Ingressa achava que o assento estava livre?"*

Experimente outros tempos de vida da cópia do mapa e rode a estreia de novo:

```bash
MAPA_TTL_S=1 docker compose up -d ingressa      # cópia quase sempre vencida
MAPA_TTL_S=300 docker compose up -d ingressa    # cópia muito antiga
MAPA_TTL_S=30 docker compose up -d ingressa     # volta ao padrão
```

Pergunta: *"qual é o tempo de vida certo? O que se ganha e o que se perde em cada extremo?"*

---

## Para fechar a aula

- O cache aliviou quem?
- O pico ainda derruba o Ingressa. O que acontece com quem chega quando o site já está no limite?
- Qual é o próximo recurso a acabar?

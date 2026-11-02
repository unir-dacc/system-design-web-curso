# Ingressa: Mini Curso de System Design para Aplicações Web

Um curso prático para devs júnior. Construímos o **Ingressa**, uma plataforma
de venda de ingressos de cinema, que começa como um monolito ingênuo e evolui
aula a aula conforme a carga cresce. Cada conceito (load balancer, cache,
filas...) entra para resolver um problema que acabamos de ver acontecer.

## Pré-requisitos

Apenas **Docker** com Compose v2.20+. Nada de Python ou k6 na máquina:
tudo roda em containers.

## Como usar

Cada etapa é uma pasta independente. Entre nela e use o Docker Compose:

```bash
cd 01-monolito

docker compose up -d --build --wait                       # sobe a etapa
docker compose run --rm --service-ports k6 run /scripts/estreia.js   # teste de carga
docker compose run --rm --service-ports k6 run -e USUARIOS=100 /scripts/estreia.js  # mais usuários por segundo
docker compose stats                                      # CPU/memória em tempo real
docker compose logs -f ingressa                           # logs do app
docker compose exec postgres psql -U ingressa             # banco
docker compose down -v                                    # derruba e apaga os dados
```

### O teste de carga

Existe **um único teste**, `shared/load-tests/estreia.js`: a abertura das vendas do
**maior filme da história**. Uma rodada, duas partes:

1. **A subida:** o público cresce em degraus (1 usuário por segundo, 2, 3...). Em cada degrau
   o teste confere se o site continua viável e descobre **até quantos usuários o Ingressa aguenta**.
2. **O pico:** por 1 minuto chegam 50 usuários por segundo (desistem se o site não carregar
   em 60 s; depois de clicar em comprar, esperam a resposta), 5 usuários muito engajados por
   segundo (nunca desistem e tentam de novo até conseguir) e robôs cambistas tentando
   furar o limite de ingressos por CPF.

- **Durante:** painel em tempo real em **http://localhost:5665**
- **Depois:** relatório visual em **`relatorios/estreia.html`**, para abrir no navegador e
  projetar (um resumo também aparece no terminal e em `relatorios/estreia.txt`).
  O relatório é gerado automaticamente pelo próprio teste.
- Toda rodada começa do zero: apaga pedidos, ingressos, reservas e cobranças
- Se nada aparecer na tela, veja `relatorios/k6.log`

O relatório traz a capacidade, o que aconteceu no pico (o caminho do usuário, os engajados,
a espera) e as metas.

Todas as etapas usam o mesmo nome de projeto (`ingressa`) e as mesmas portas.
Antes de trocar de etapa, rode `docker compose down -v` na pasta da etapa anterior.

Para ver o que mudou entre duas etapas:

```bash
git diff --no-index <etapa-anterior> <etapa-seguinte>
```

Cada etapa tem um `DEMO.md`, o roteiro da aula com os comandos na ordem.

## Estrutura

```
├── shared/                      # igual para todas as etapas
│   ├── compose.externos.yml     # sistemas externos com limites fixos
│   ├── gateway-pagamento/       # gateway simulado (lento, configurável)
│   ├── sistema-cinema/          # sistema de assentos legado (lento, com fila)
│   ├── load-tests/estreia.js    # o teste de carga (k6)
│   └── seed/catalogo.json       # filmes, salas e sessões
├── 01-monolito/                 # cada etapa é completa e roda sozinha
│   ├── app/
│   ├── docker-compose.yml
│   └── DEMO.md
├── 02-cache/                    # cache do mapa de assentos (Redis)
└── 03-async/                    # async/await com o mesmo hardware
```

## Comparação justa entre etapas

Todos os `docker-compose.yml` limitam CPU e memória. As regras:

1. **Sistemas externos são idênticos em todas as etapas** (vêm de `shared/compose.externos.yml`).
   Comportamento controlado por configuração, não por hardware.
2. **Cada etapa declara o orçamento do Ingressa** no topo do seu compose.
3. **Cada medição começa do zero**: os testes de carga limpam o estado antes de rodar.
4. **O gerador de carga (k6) roda com 2 CPUs fixas**, num container separado do sistema testado.

| Componente | CPU | Memória | Observação |
|------------|-----|---------|------------|
| gateway-pagamento | 0.5 | 128 MB | latência ~1,2 s, 5% recusa |
| sistema-cinema | 0.5 | 128 MB | mapa ~800 ms, reserva ~600 ms, confirmação ~400 ms, **10 requisições simultâneas** |
| mailpit | 0.25 | 128 MB | SMTP falso, UI em :8025 |
| k6 | 2 | — | gerador de carga |

## Simuladores: mudando o comportamento ao vivo

O jeito mais visual é pelo Swagger: **http://localhost:8001/docs** (gateway) e
**http://localhost:8002/docs** (cinema), nas rotas `/admin/config`. Pelo terminal:

```bash
curl localhost:8001/admin/config                 # ver a configuração do gateway

# gateway lento / com 30% de erro 500 / com 10% de requisições que nunca respondem
curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"latencia_ms": 5000}'
curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"taxa_erro": 0.3}'
curl -X PATCH localhost:8001/admin/config -H "Content-Type: application/json" -d '{"taxa_travamento": 0.1}'

# cinema ainda mais limitado
curl -X PATCH localhost:8002/admin/config -H "Content-Type: application/json" -d '{"max_concorrencia": 2}'

curl localhost:8002/admin/estado                 # fila do cinema e assentos por sessão
```

Cartões de teste: `tok_aprovado` (sempre aprova), `tok_recusado` (sempre recusa), qualquer outro (5% de recusa).

## Regras de negócio do Ingressa

- **Meia-entrada** custa 50% e tem cota de **40%** da sala (Lei 12.933/2013)
- **Taxa de conveniência** de 10%
- **Limite de 6 ingressos por CPF** por sessão
- **CPF validado** pelos dígitos verificadores
- Assentos **reservados** no cinema durante o pagamento (expiram em 10 min)
- Ingresso com **QR code**, enviado por **e-mail**

## Endereços

| Serviço | URL |
|---------|-----|
| Ingressa (Swagger) | http://localhost:8000/docs |
| Gateway de pagamento | http://localhost:8001/docs |
| Sistema do cinema | http://localhost:8002/docs |
| E-mails (Mailpit) | http://localhost:8025 |
| Painel do k6 (durante um teste) | http://localhost:5665 |

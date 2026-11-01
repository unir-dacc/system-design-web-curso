# Ingressa: Mini Curso de System Design para Aplicações Web

Um curso prático para devs júnior. Construímos o **Ingressa**, uma plataforma
de venda de ingressos de cinema, que começa como um monolito ingênuo e evolui
aula a aula conforme a carga cresce. Cada conceito (load balancer, cache,
filas...) entra para resolver um problema que acabamos de ver acontecer.

## Pré-requisitos

Apenas **Docker** (com Compose) e **make**. Nada de Python ou k6 na máquina:
tudo roda em containers.

## Como usar

```bash
make help                                  # lista os comandos
make up STEP=01                            # sobe a etapa do zero
make load STEP=01 SCRIPT=abertura-vendas   # teste de carga
make stats                                 # CPU/memória em tempo real
make diff FROM=01 TO=02                    # o que mudou entre etapas
make down                                  # derruba tudo
```

Cada etapa tem um `DEMO.md`, o roteiro da aula com os comandos na ordem.

## Estrutura

```
├── Makefile
├── shared/                      # igual para todas as etapas
│   ├── compose.externos.yml     # sistemas externos com limites fixos
│   ├── gateway-pagamento/       # gateway simulado (lento, configurável)
│   ├── sistema-cinema/          # sistema de assentos legado (lento, com fila)
│   ├── load-tests/              # scripts k6
│   └── seed/catalogo.json       # filmes, salas e sessões
└── 01-monolito/                 # cada etapa é completa e roda sozinha
    ├── app/
    ├── docker-compose.yml
    └── DEMO.md
```

## Comparação justa entre etapas

Todos os `docker-compose.yml` limitam CPU e memória. As regras:

1. **Sistemas externos são idênticos em todas as etapas** (vêm de `shared/compose.externos.yml`).
   Comportamento controlado por configuração, não por hardware.
2. **Cada etapa declara o orçamento do Ingressa** no topo do seu compose.
3. **`make up` sempre começa do zero** (banco e simuladores limpos).
4. **O gerador de carga (k6) roda com 2 CPUs fixas**, separado do sistema testado.

| Componente | CPU | Memória | Observação |
|------------|-----|---------|------------|
| gateway-pagamento | 0.5 | 128 MB | latência ~1,2 s, 5% recusa |
| sistema-cinema | 0.5 | 128 MB | mapa ~800 ms, reserva ~600 ms, confirmação ~400 ms, **10 requisições simultâneas** |
| mailpit | 0.25 | 128 MB | SMTP falso, UI em :8025 |
| k6 | 2 | — | gerador de carga |

## Simuladores: mudando o comportamento ao vivo

```bash
make gateway                                   # ver configuração atual
make gateway CONFIG='{"latencia_ms": 5000}'    # gateway lento
make gateway CONFIG='{"taxa_erro": 0.3}'       # 30% de erro 500
make gateway CONFIG='{"taxa_travamento": 0.1}' # 10% nunca respondem
make cinema  CONFIG='{"max_concorrencia": 2}'  # cinema ainda mais limitado
make estado                                    # fila do cinema e assentos por sessão
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

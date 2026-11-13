# Ingressa: Mini Curso de System Design para Aplicações Web

Um curso prático para devs júnior. Construímos o **Ingressa**, uma plataforma
de venda de ingressos de cinema, que começa como um monolito ingênuo e evolui
aula a aula conforme a carga cresce. Cada conceito (load balancer, cache,
filas...) entra para resolver um problema que acabamos de ver acontecer.

## As aulas

Cada etapa resolve o problema que a etapa anterior mostrou no teste de carga.
A ordem é a ordem lógica do curso.

| Etapa | Tema | O que entra |
|-------|------|-------------|
| `01-monolito` | O ponto de partida | FastAPI síncrono, Postgres, regras de negócio corretas desde já |
| `02-cache` | O trabalho repetido | Redis guardando as respostas que são iguais para todo mundo |
| `03-nginx` | A CPU que sobrava | Nginx balanceando 2 backends (o GIL do Python) |
| `04-rate-limit` | O excesso no pico | o Nginx limita as requisições em andamento de cada endpoint |
| `04b-async` | Esperar sem prender uma thread | a 04 com o Ingressa assíncrono: quando o async ajuda, e quando não |
| `04c-em-go` | A linguagem sem a arquitetura | a 04 reescrita em Go: dá para trocar a fila e a sala de espera por uma linguagem mais rápida? |
| `05-fila` | O que não precisa ser feito agora | a compra vai para uma fila; um worker conclui e avisa por e-mail |
| `06-sala-de-espera` | Quem não pode ser perdido | senha, porteiro e passe: quem chega no pico espera a vez |
| `07-mais-hardware` | O que o dinheiro resolve | a 06 com 8 CPUs e 8 GB, numa estreia 5 vezes maior |
| `08-go` | A linguagem | a 07 reescrita em Go, com o mesmo hardware e o mesmo teste |

## Pré-requisitos

Apenas **Docker** com Compose v2.20+. Nada de Python ou k6 na máquina:
tudo roda em containers.

## Como usar

Cada etapa é uma pasta independente. A partir da raiz do repositório, entre nela e use o Docker Compose:

```bash
cd 01-monolito

docker compose up -d --build --wait                       # sobe a etapa
docker compose run --rm --service-ports k6 run /scripts/estreia.js   # teste de carga
docker compose run --rm --service-ports k6 run -e USUARIOS=200 /scripts/estreia.js  # pico maior
docker compose stats                                      # CPU/memória em tempo real
docker compose logs -f ingressa                           # logs do app
docker compose exec postgres psql -U ingressa             # banco
docker compose --profile observar up -d pghero            # painel do banco em http://localhost:8080
docker compose down -v                                    # derruba e apaga os dados
```

### O teste de carga

Existe **um único teste**, `shared/load-tests/estreia.js`: a abertura das vendas do
**maior filme da história**, com 60 sessões em salas IMAX de 400 lugares (24.000 lugares,
para a subida não esgotar os ingressos antes do pico).

O público é como o de uma loja de verdade: todo usuário abre a programação e olha o mapa de
uma sessão, mas **a maioria só olha**. De cada 10, 7 dão uma olhada em outra sessão e vão
embora, e 3 compram. Uma rodada, duas partes:

1. **A subida:** o público cresce em degraus de 10 s, de ~1,5× cada (4 usuários por segundo, 8, 12, 16, 24...
   até o maior degrau abaixo do pico). Em cada degrau o teste confere se o site continua viável e descobre **até quantos usuários o Ingressa aguenta**.
2. **O pico:** por 30 segundos chegam 120 usuários por segundo (desistem se o site não carregar
   em 60 s; depois de clicar em comprar, esperam a resposta), 12 usuários muito engajados por
   segundo (nunca desistem e tentam de novo até conseguir) e robôs cambistas tentando
   furar o limite de ingressos por CPF.

- **Durante:** painel em tempo real em **http://localhost:5665**
- **Depois:** relatório visual em **`relatorios/estreia.html`**, para abrir no navegador e
  projetar (um resumo também aparece no terminal e em `relatorios/estreia.txt`).
  O relatório é gerado automaticamente pelo próprio teste.
- Toda rodada começa do zero: apaga pedidos, ingressos, reservas e cobranças
- Se nada aparecer na tela, veja `relatorios/k6.log`

O relatório traz a capacidade, a progressão das vendas até o pico, o que aconteceu com cada
público no pico, a velocidade de cada endpoint, as metas e a comparação com as etapas anteriores.

Todas as etapas usam o mesmo nome de projeto (`ingressa`) e as mesmas portas.
Antes de trocar de etapa, rode `docker compose down -v` na pasta da etapa anterior.

Para ver o que mudou entre duas etapas:

```bash
git diff --no-index <etapa-anterior> <etapa-seguinte>
```

Cada etapa tem um `README.md`, o roteiro da aula com os comandos na ordem (o GitHub mostra ele ao abrir a pasta da etapa).

## Endereços

| Serviço | URL |
|---------|-----|
| Ingressa (Swagger) | http://localhost:8000/docs |
| Gateway de pagamento (Swagger) | http://localhost:8001/docs |
| Sistema do cinema (Swagger) | http://localhost:8002/docs |
| E-mails (Mailpit) | http://localhost:8025 |
| Painel do k6 (durante um teste) | http://localhost:5665 |
| Painel do banco (pgHero, opcional) | http://localhost:8080 |

## Os sistemas externos

O Ingressa depende de três sistemas que não são dele. São simulados, iguais em todas as etapas
e ficam fora do orçamento do Ingressa. Os tempos variam ±30% a cada chamada, como num sistema de
verdade, e tudo pode ser mudado ao vivo (veja [Simuladores](#simuladores-mudando-o-comportamento-ao-vivo)).

### Sistema do cinema · http://localhost:8002/docs

O sistema da rede de cinemas: é ele quem manda nos assentos.

| | |
|---|---|
| O que faz | Mostra o mapa da sala, reserva, confirma e cancela assentos |
| Tempo de resposta | mapa ~50 ms, reserva ~40 ms, confirmação ~30 ms |
| Quanto aguenta | até 200 atendimentos ao mesmo tempo; acima disso, o excedente espera numa fila |
| Erros | nenhum no padrão (configurável: `taxa_erro` devolve 503) |
| Garantias | a reserva é atômica: nunca vende o mesmo assento duas vezes. Reserva não confirmada expira em 10 min |
| Hardware | 2 CPUs, 256 MB |

### Gateway de pagamento · http://localhost:8001/docs

Cobra o cartão. Aguenta muita carga, mas cada cobrança demora (antifraude, bandeira do cartão).

| | |
|---|---|
| O que faz | Cobra o cartão e responde se aprovou ou recusou |
| Tempo de resposta | **~3 s por cobrança** (entre 2,1 s e 3,9 s) |
| Quanto aguenta | não limita as cobranças simultâneas: cada uma só espera, então cabem muitas ao mesmo tempo |
| Recusas | 5% dos cartões; `tok_aprovado` sempre aprova, `tok_recusado` sempre recusa |
| Erros | nenhum no padrão (configurável: `taxa_erro` devolve 500, `taxa_travamento` nunca responde) |
| Garantias | o cabeçalho `Idempotency-Key` evita cobrar duas vezes a mesma compra |
| Hardware | 0,5 CPU, 128 MB |

Do lado do Ingressa, a cobrança tem um limite de 10 s. Passou disso, ele pergunta ao gateway se a
cobrança aconteceu antes de liberar o assento.

### E-mails (Mailpit) · http://localhost:8025

Um servidor de e-mail falso, com uma página para ver as mensagens: é onde chegam as confirmações
com os QR codes. Guarda até 5.000 mensagens. Hardware: 0,25 CPU, 128 MB.

## Os diagramas

Cada etapa tem o desenho da sua arquitetura: o público, as peças do Ingressa com a CPU e a memória
de cada uma, e os sistemas externos. A peça nova de cada etapa está em amarelo. O link abre o
desenho no Excalidraw, para desenhar por cima durante a aula (o `README.md` de cada etapa também tem
o link).

| Etapa | Diagrama |
|-------|----------|
| `01-monolito` | [abrir no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/01-monolito/arquitetura.excalidraw) |
| `02-cache` | [abrir no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/02-cache/arquitetura.excalidraw) |
| `03-nginx` | [abrir no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/03-nginx/arquitetura.excalidraw) |
| `04-rate-limit` | [abrir no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/04-rate-limit/arquitetura.excalidraw) |
| `04b-async` | [abrir no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/04b-async/arquitetura.excalidraw) |
| `04c-em-go` | [abrir no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/04c-em-go/arquitetura.excalidraw) |
| `05-fila` | [abrir no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/05-fila/arquitetura.excalidraw) |
| `06-sala-de-espera` | [abrir no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/06-sala-de-espera/arquitetura.excalidraw) |
| `07-mais-hardware` | [abrir no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/07-mais-hardware/arquitetura.excalidraw) |
| `08-go` | [abrir no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/08-go/arquitetura.excalidraw) |

## Os slides

Os slides do mini curso estão em [`slides/mini-curso-system-design.pdf`](slides/mini-curso-system-design.pdf):
a abertura e os conceitos básicos (como a web funciona, HTTP, APIs, o que acontece dentro do
servidor, banco de dados, como medir, teste de carga e containers), antes do protótipo.

## Estrutura

```
system-design-web-curso/
├── slides/                      # os slides do mini curso, em PDF
├── shared/                      # igual para todas as etapas
│   ├── compose.externos.yml     # sistemas externos com limites fixos
│   ├── gateway-pagamento/       # gateway de pagamento simulado (lento)
│   ├── sistema-cinema/          # sistema de assentos da rede de cinemas (rápido)
│   ├── load-tests/estreia.js    # o teste de carga (k6)
│   └── seed/catalogo.json       # filmes, salas e sessões
├── 01-monolito/                 # cada etapa é completa e roda sozinha
│   ├── app/
│   ├── docker-compose.yml
│   ├── arquitetura.excalidraw   # o diagrama da etapa (abra no Excalidraw)
│   └── README.md                # o roteiro da aula
├── 02-cache/                    # cache das respostas iguais para todos (Redis)
├── 03-nginx/                    # Nginx na frente de 2 backends (o orçamento onde está o gargalo)
├── 04-rate-limit/               # o Nginx limita as requisições em andamento por endpoint
├── 04b-async/                   # a 04 com o Ingressa assíncrono (async/await)
├── 04c-em-go/                   # a 04 reescrita em Go: a linguagem contra a arquitetura
├── 05-fila/                     # a compra vai para uma fila, e um worker a conclui
├── 06-sala-de-espera/           # quem chega no pico pega uma senha e espera a vez
├── 07-mais-hardware/            # o grande final: a 06 com 8 CPUs, 8 GB e um pico de 600/s
└── 08-go/                       # a 07 reescrita em Go: mesmo hardware, mesmo teste
```

## Comparação justa entre etapas

Todos os `docker-compose.yml` limitam CPU e memória. As regras:

1. **Sistemas externos são idênticos em todas as etapas** (vêm de `shared/compose.externos.yml`).
   Comportamento controlado por configuração, não por hardware.
2. **O Ingressa tem sempre o mesmo orçamento: 2 CPUs e 2 GB de RAM**, somando tudo o que é
   dele (app, banco e o que entrar depois, como Redis, worker ou Nginx). Uma peça nova não
   ganha hardware novo: ela divide o orçamento com as outras. Cada etapa mostra a divisão
   no topo do seu compose. Os ganhos vêm da arquitetura, nunca de máquina maior. A exceção é
   a etapa 07 (e a 08, que a repete em Go): ela existe para mostrar o que mais hardware faz.
3. **Cada medição começa do zero**: os testes de carga limpam o estado antes de rodar.
4. **O gerador de carga (k6) roda num container separado**, sem limite de CPU, fora do orçamento.

| Componente | CPU | Memória | Observação |
|------------|-----|---------|------------|
| gateway-pagamento | 0.5 | 128 MB | **lento**: ~3 s por cobrança, 5% recusa |
| sistema-cinema | 2 | 256 MB | **rápido**: mapa ~50 ms, reserva ~40 ms, confirmação ~30 ms, até 200 atendimentos simultâneos |
| mailpit | 0.25 | 128 MB | SMTP falso, UI em :8025 |
| k6 | sem limite | — | gerador de carga |

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

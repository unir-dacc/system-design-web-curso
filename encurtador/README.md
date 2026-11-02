# Encurtador de URL: os problemas de banco de dados

O segundo lab do curso. Um encurtador de URL parece simples: guardar um link,
devolver um código curto, redirecionar quem clica. Até o dia em que todo mundo compartilha links ao mesmo tempo.
Este lab usa o encurtador para mostrar, um por um, os problemas de banco de
dados que aparecem quando a carga cresce.

## Como usar

Cada etapa é uma pasta independente. A partir da raiz do repositório:

```bash
cd encurtador/01-monolito

docker compose up -d --build --wait                              # sobe a etapa (a primeira vez cria 1 milhão de links)
docker compose run --rm --service-ports k6 run /scripts/movimento.js # teste de carga
docker compose stats                                             # CPU/memória em tempo real
docker compose exec postgres psql -U encurtador                  # banco
docker compose down -v                                           # derruba e apaga os dados
```

## As aulas

| Etapa | Tema |
|-------|------|
| `01-monolito` | O ponto de partida: FastAPI síncrono e Postgres |

## O encurtador

| Rota | O que faz |
|------|-----------|
| `POST /links` | cria um link curto: `{"url": "https://..."}` |
| `GET /{codigo}` | redireciona para o link original (302) e conta o clique |
| `GET /links/{codigo}/estatisticas` | quantos cliques o link teve |

O código curto tem 7 caracteres em base 62 (`0-9`, `a-z`, `A-Z`) e vem do número
do link, embaralhado: nunca se repete e não dá para adivinhar os links dos
outros contando 1, 2, 3...

Na primeira subida, o encurtador cria **1 milhão de links** (para mudar:
`LINKS_INICIAIS=500000 docker compose up -d`).

## O teste de carga

Um único teste, `shared/load-tests/movimento.js`: **o dia em que o encurtador bombou**.
Um evento faz todo mundo compartilhar links ao mesmo tempo. Uma rodada, duas partes:

1. **A subida:** as requisições chegam em degraus (5 por segundo, 10, 20, 30...).
   Em cada degrau o teste confere se o encurtador continua viável e descobre
   **quantas requisições por segundo ele aguenta**.
2. **O pico:** por 1 minuto chegam 2.000 requisições por segundo: de cada 100, 95 são
   cliques, 4 criam links e 1 abre as estatísticas. Junto, 100 robôs por segundo tentam
   códigos aleatórios, que quase nunca existem. Quem clica espera no máximo 5 s.

**A procura pelos links segue uma curva normal (um sino), estreita.** O teste sorteia mil
links que existem: os poucos do centro da curva concentram os cliques, os do meio-termo
recebem bem menos, e os das pontas são muito raramente acessados.

- **Durante:** painel em tempo real em **http://localhost:5665**
- **Depois:** relatório em **`relatorios/movimento.html`**, com a capacidade, a progressão
  até o pico, a velocidade de cada endpoint, a conferência dos cliques (quantos foram
  redirecionados e quantos o encurtador contou) e a comparação com as etapas anteriores.

## Comparação justa entre etapas

O encurtador tem sempre o mesmo orçamento: **2 CPUs e 2 GB de RAM**, somando tudo o
que é dele. Uma peça nova divide o orçamento com as outras. Os ganhos vêm da
arquitetura, nunca de máquina maior. O gerador de carga (k6) fica fora do orçamento.

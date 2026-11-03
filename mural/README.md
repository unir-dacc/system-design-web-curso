# Mural: os problemas de banco de dados

Uma rede social com feed. Parece simples: seguir pessoas, publicar, curtir,
comentar. Mas montar um feed obriga o banco a cruzar quem eu sigo com milhões
de posts, ordenar, paginar e contar curtidas, e a rede é desigual: poucas
celebridades têm dezenas de milhares de seguidores. Este lab usa o Mural para
mostrar, um por um, os problemas de banco de dados que aparecem quando a carga
cresce.

## Como usar

Cada etapa é uma pasta independente. A partir da raiz do repositório:

```bash
cd mural/01-monolito

docker compose up -d --build --wait                          # sobe a etapa (a primeira vez cria a rede inteira)
docker compose run --rm --service-ports k6 run /scripts/viral.js   # teste de carga
docker compose stats                                         # CPU/memória em tempo real
docker compose exec postgres psql -U mural                   # banco
docker compose down -v                                       # derruba e apaga os dados
```

## As aulas

| Etapa | Tema |
|-------|------|
| `01-monolito` | O ponto de partida: FastAPI síncrono, SQLAlchemy ORM do jeito mais direto, e Postgres |
| `02-indices` | O banco no limite: os índices que as consultas do Mural precisam (e por que a ForeignKey não cria um) |

## O Mural

| Rota | O que faz |
|------|-----------|
| `GET /feed?usuario_id=&pagina=` | os posts de quem o usuário segue, dos mais novos para os mais antigos, de 20 em 20 |
| `GET /usuarios/{id}` | o perfil: o usuário e os posts dele |
| `GET /posts/{id}` | o post com os comentários mais recentes |
| `POST /posts` | publica: `{"usuario_id": 42, "texto": "..."}` |
| `POST /posts/{id}/curtidas` | curte: `{"usuario_id": 42}` (201; se já tinha curtido, 200) |
| `POST /posts/{id}/comentarios` | comenta: `{"usuario_id": 42, "texto": "..."}` |

Sem login, para simplificar: quem escreve diz quem é no corpo da requisição.

Na primeira subida, o Mural cria a rede inicial: **100 mil usuários, ~5 milhões de
"segue", 1 milhão de posts, ~5 milhões de curtidas e 500 mil comentários**. A rede é
desigual como uma de verdade: cada um segue de 1 a 300 pessoas, poucas celebridades
concentram os seguidores, e poucos posts concentram as curtidas. Para mudar o tamanho:
`USUARIOS_INICIAIS`, `POSTS_INICIAIS`, `CURTIDAS_INICIAIS` e `COMENTARIOS_INICIAIS`
(veja o `docker-compose.yml`).

## O teste de carga

Um único teste, `shared/load-tests/viral.js`: **o dia em que um post viralizou**.
A maior celebridade da rede publica um post que todo mundo quer ver. Uma rodada, duas partes:

1. **A subida:** as requisições chegam em degraus (2 por segundo, 5, 10, 20...).
   Em cada degrau o teste confere se o Mural continua viável e descobre
   **quantas requisições por segundo ele aguenta**.
2. **O pico:** por 1 minuto chegam 1.000 requisições por segundo. De cada 100, 70 abrem
   o feed (a maioria fica na primeira página, poucos rolam bem fundo), 10 abrem um perfil,
   10 abrem um post com os comentários, 7 curtem, 2 publicam e 1 comenta. A maior parte
   das curtidas, dos comentários e das visitas a posts vai para o post viral. Quem espera
   desiste depois de 5 s.

- **Durante:** painel em tempo real em **http://localhost:5665**
- **Depois:** relatório em **`relatorios/viral.html`**, com a capacidade, a progressão até
  o pico, a velocidade de cada endpoint, a conferência das curtidas do post viral (quantas
  foram aceitas e quantas o Mural mostra) e a comparação com as etapas anteriores.

## Comparação justa entre etapas

O Mural tem sempre o mesmo orçamento: **2 CPUs e 2 GB de RAM**, somando tudo o que é
dele. Uma peça nova divide o orçamento com as outras. Os ganhos vêm da arquitetura,
nunca de máquina maior. O gerador de carga (k6) fica fora do orçamento.

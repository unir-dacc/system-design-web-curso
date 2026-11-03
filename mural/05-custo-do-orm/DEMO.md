# Mural · Aula 05: O custo do ORM

> **Objetivo:** com o feed bem escrito, o banco ficou com folga e o app virou o
> gargalo. Medir onde o app gasta a CPU dele e mostrar que o ORM tem um preço:
> montar a consulta e criar um objeto para cada linha, a cada requisição. Nas
> rotas mais acessadas, trocar o ORM por SQL escrito uma vez só. Sem peça nova
> e com o mesmo hardware.

```
            ┌──────────────────────────┐   leituras: SQL    ┌───────────────────────────┐
 usuário ──▶│  Mural (1 processo)      │──────────────────▶ │ Postgres                  │
            │  FastAPI síncrono        │   escritas: ORM    │ os mesmos índices da 02   │
            │  1 CPU / 1 GB            │                    │ 1 CPU / 1 GB              │
            └──────────────────────────┘                    └───────────────────────────┘
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`mural/05-custo-do-orm/`).

```bash
docker compose -f ../04-paginacao/docker-compose.yml down -v     # as etapas usam os mesmos nomes
docker compose up -d --build --wait
docker build -t py-spy - <<'EOF'
FROM python:3.12-slim
RUN pip install py-spy
EOF
```

Rode o teste das etapas anteriores antes da aula: o relatório desta etapa compara com o último resultado delas.
Rode também o teste desta etapa uma vez: logo depois da subida, o banco ainda não tem nada na memória.

---

## 1. Onde a 04 parou

Abra `../04-paginacao/relatorios/viral.html` e relembre o `docker compose stats` daquela rodada.

Pergunta para a turma: *"o banco tinha folga. Então o que o app estava fazendo com a CPU dele?"*

## 2. Medindo em vez de chutar

Suba a 04 de novo e, com o teste rodando, grave onde o app gasta a CPU no degrau de 100/s. O `py-spy`
olha o processo Python por fora, sem mudar o código, e o `--gil` conta só o que de fato está usando a CPU:

```bash
cd ../04-paginacao && docker compose up -d --build --wait
docker compose run --rm k6 run /scripts/viral.js > /dev/null &
sleep 140     # o degrau de 100/s começa uns 135 s depois do início
docker run --rm --pid=container:mural-app-1 --cap-add SYS_PTRACE -v "$PWD/relatorios:/out" py-spy \
  py-spy record -p 1 --gil -d 10 -o /out/perfil.svg
wait
xdg-open relatorios/perfil.svg
```

👉 **Observe:** no gráfico, a largura de cada bloco é o tempo de CPU. Quanto é do código do Mural
(`app/routes/`)? Quanto é do SQLAlchemy? E dentro do SQLAlchemy, quanto é montar a consulta (`sql/`)
e quanto é criar os objetos (`orm/`)?

Pergunta: *"o banco responde o feed em poucos milissegundos. Quanto tempo o app gasta para pedir e para receber?"*

Depois, volte para esta pasta:

```bash
cd ../05-custo-do-orm && docker compose up -d --build --wait
```

## 3. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `app/routes/feed.py` | O feed e o perfil em SQL, escrito uma vez só, no topo do arquivo. A consulta do feed é a mesma da 04 |
| `app/routes/feed.py` | O autor e as curtidas vêm na mesma consulta: uma ida ao banco por página |
| `app/routes/posts.py` | A página do post também em SQL. As escritas continuam pelo ORM. Por quê? |
| `app/routes/esquemas.py` | A linha do banco vira a resposta direto, sem passar por um objeto `Post` |

Pergunta: *"as curtidas são contadas fora da subconsulta `pagina`. O que mudaria se fossem contadas dentro?"*

Pergunta: *"o que se perde trocando o ORM por SQL? Quando vale a pena?"*

## 4. O dia em que um post viralizou

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/viral.js
xdg-open relatorios/viral.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 04? O banco ficou mais rápido? |
| A progressão | Em qual degrau as atendidas param de acompanhar as que chegam agora? |
| A velocidade de cada endpoint | Quais endpoints ganharam? E as escritas, que continuaram pelo ORM? |

👉 **Observe também:** no `docker compose stats`, a CPU do app e do Postgres. Quem chega no limite primeiro agora?

Grave o perfil do app desta etapa, como na seção 2 (dentro desta pasta), e compare os dois gráficos.

Anote o número do topo: ele vai ser comparado com o das próximas etapas.

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- O que limita o Mural agora?
- As curtidas ainda são contadas na hora. O post viral recebe milhares por minuto: quanto custa contar?
- E se o app tivesse mais de um processo? De onde viria a CPU, se o orçamento é o mesmo?

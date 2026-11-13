# Aula 08: Mais hardware (o grande final)

> **Objetivo:** pegar a arquitetura que a turma construiu, dar a ela 4 vezes
> mais hardware e enfrentar uma estreia 5 vezes maior. E discutir o que o
> hardware resolve, e o que só a arquitetura resolveu.

```
                    ┌──────────────────────────────────────────────┐
 usuários ──▶ sala de espera ──▶ Nginx ──▶ 6 backends ──▶ fila ──▶ worker
                    │                         │                    │
                    └──────── Redis ──────────┴──── Postgres ──────┘
```

A arquitetura é a mesma da etapa 06. Mudam o hardware (8 CPUs e 8 GB, em vez de 2 CPUs e 2 GB) e o tamanho da estreia no teste.

**[🖊️ Abrir o diagrama desta etapa no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/08-mais-hardware/arquitetura.excalidraw)**,
para desenhar por cima durante a aula. A peça nova da etapa está em amarelo.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`08-mais-hardware/`).

```bash
docker compose down -v          # garante que começa do zero
docker compose up -d --build --wait
```

Rode a estreia das etapas anteriores antes da aula: o relatório desta etapa compara com o último resultado delas.

Esta rodada é pesada: o gerador de carga cria dezenas de milhares de usuários. Feche o que não precisar na máquina.

---

## 1. A pergunta da primeira aula

Volte ao quadro da aula 01. Lá ficou a pergunta: *"se a gente der 4 CPUs para o Ingressa, melhora?"*

Pergunta para a turma: *"e se a gente tivesse dado 8 CPUs para o Ingressa da aula 01, sem mudar nada no código? O que teria acontecido?"*

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `docker-compose.yml` | A nova divisão: 6 backends, um worker maior, um Postgres maior. Quanto foi para cada peça, e por quê? |
| `docker-compose.yml` (Postgres) | `max_connections`: por que o padrão do banco deixou de bastar? |
| `docker-compose.yml` (k6) | O tamanho da estreia: `USUARIOS` e `DEGRAUS` |
| `nginx/templates/ingressa.conf.template` | Os limites cresceram junto com o hardware |

Pergunta: *"de onde vieram os números de cada peça? O que aconteceria se todo o hardware novo fosse para os backends?"*

## 3. A grande estreia

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | Compare a 08 com a 06 e com a 01. Quanto do ganho veio do hardware, e quanto da arquitetura? |
| A progressão das vendas | Até onde as vendas acompanham a procura agora? |
| O pico: cada público | Alguém encontrou a sessão esgotada? O que isso quer dizer para o cinema? |
| O pico: o sistema | A fila de compras e a sala de espera: até quanto cresceram? |

👉 **Observe também:** no `docker compose stats`, qual peça chega primeiro no limite agora.

Pergunta: *"com 4 vezes mais hardware, o Ingressa aguentou 4 vezes mais gente? Por quê?"*

## 4. E se o hardware novo fosse para o Ingressa da 01?

Para discutir sem rodar: o que segurava a 01 era o código esperando o gateway e refazendo a mesma resposta para todo mundo.

Pergunta: *"quantas CPUs um processo Python da 01 consegue usar? E quantas threads ele tem para esperar o gateway?"*

Pergunta: *"qual das etapas daria para fazer de graça, sem pagar por mais nenhuma máquina? E qual só fez sentido com hardware?"*

## Onde o banco gastou o tempo

Suba o painel do banco, o pgHero, e abra http://localhost:8080:

```bash
docker compose --profile observar up -d pghero
```

Depois de um teste, a aba **Queries** lista as consultas da rodada pelo tempo total que elas
tomaram do banco (as estatísticas são zeradas no começo de cada teste). O mesmo, no terminal:

```bash
docker compose exec postgres psql -U ingressa -c "SELECT calls AS vezes, round(mean_exec_time::numeric, 1) AS media_ms,
  round((100 * total_exec_time / sum(total_exec_time) OVER ())::numeric, 1) AS pct_do_tempo, left(query, 60) AS consulta
  FROM pg_stat_statements WHERE query NOT ILIKE '%pg_stat%' ORDER BY total_exec_time DESC LIMIT 5"
```

Pergunta: *"qual consulta tomou mais tempo do banco? Ela é lenta, ou roda muitas vezes?"*

---

## Para fechar o curso

Monte com a turma a linha do tempo das etapas, com o que cada uma atacou:

- 01 Monolito: o ponto de partida
- 02 Cache: o trabalho repetido
- 03 Nginx: a CPU que sobrava
- 04 Rate limit: o excesso na porta
- 05 Fila com worker: o que não precisa ser feito agora
- 06 Sala de espera: quem não pode ser perdido
- 07 Mais hardware: o que o dinheiro resolve

Pergunta final: *"se vocês tivessem que escolher só duas dessas etapas para um site de verdade, quais seriam?"*

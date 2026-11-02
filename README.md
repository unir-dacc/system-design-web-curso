# Mini Curso de System Design para Aplicações Web

Um curso prático para devs júnior. Cada lab é uma aplicação que começa
ingênua e evolui etapa por etapa, conforme a carga cresce. Cada conceito
(cache, balanceador, filas, banco de dados...) entra para resolver um
problema que a turma acabou de ver acontecer num teste de carga.

## Os labs

| Lab | A aplicação | O que ele ensina |
|-----|-------------|------------------|
| [`ingressa/`](ingressa/) | **Ingressa**: venda de ingressos de cinema na estreia do maior filme da história | picos de acesso, cache, balanceamento, rate limit, filas, sala de espera, hardware e linguagem |
| [`encurtador/`](encurtador/) | Um **encurtador de URL** no dia de mais movimento | os problemas de banco de dados: índices, contadores disputados, conexões, réplicas, crescimento das tabelas *(em construção)* |

Cada lab tem o seu próprio `README.md`, e cada etapa tem um `DEMO.md`: o roteiro da aula, com os comandos na ordem.

## Pré-requisitos

Apenas **Docker** com Compose v2.20+. Nada de Python ou k6 na máquina:
tudo roda em containers.

## Como funciona um lab

- **Cada etapa é uma pasta independente** e roda sozinha: `cd <lab>/<etapa>` e `docker compose up -d --build --wait`.
- **Um único teste de carga por lab**, que gera um relatório em `relatorios/` comparando a etapa com as anteriores.
- **O hardware é fixo**: o que melhora de uma etapa para outra é a arquitetura, nunca uma máquina maior.
- **Os roteiros não têm spoilers**: os resultados aparecem quando a turma roda o teste.

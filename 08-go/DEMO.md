# Aula 08: A etapa 07 reescrita em Go

> **Objetivo:** responder com medição a pergunta que todo dev faz um dia:
> *"e se fosse em outra linguagem?"*. A arquitetura, o hardware e o teste são
> os da etapa 07. Só a linguagem do Ingressa muda.

```
 usuários ──▶ sala de espera ──▶ Nginx ──▶ 6 backends (Go) ──▶ fila ──▶ worker (Go)
                    │                            │                       │
                    └────────── Redis ───────────┴────── Postgres ───────┘
```

O Nginx, o Postgres, o Redis, os sistemas externos, o hardware (8 CPUs e 8 GB) e a estreia (600 usuários por segundo) são exatamente os da 07.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`08-go/`).

```bash
docker compose down -v          # garante que começa do zero
docker compose up -d --build --wait
```

Rode a estreia da etapa 07 antes da aula: o relatório desta etapa compara com o último resultado dela.

---

## 1. O mesmo Ingressa, em outra língua

Abra lado a lado um arquivo da 07 e o equivalente aqui:

| Python (`../07-mais-hardware/app/`) | Go (`./`) |
|-------------------------------------|-----------|
| `compra.py` | `compra.go` |
| `sala.py` e `routes/sala.py` | `sala.go` e `rotas.go` |
| `fila.py` e `worker.py` | `fila.go` e `worker.go` |
| `cache.py` | `cache.go` |

Pergunta para a turma: *"o que é igual nos dois? O que o Go obriga a escrever que o Python escondia?"*

Pergunta: *"em Python, um processo usava no máximo 1 CPU, por causa do GIL. E em Go? Por que a 07 tinha 6 backends, e esta também tem?"*

## 2. As mesmas respostas

```bash
curl -s -X POST localhost:8000/admin/reset > /dev/null
curl -s -X POST localhost:8000/sala; echo
curl -s localhost:8000/sala/1; echo                 # repita até liberar
curl -s -H 'X-Passe: <cole o passe aqui>' localhost:8000/sessoes/7/assentos | head -c 200; echo
```

👉 **Observe:** compare o passe e as respostas com as da etapa 07. O teste de carga é o mesmo, e não sabe em que linguagem o Ingressa foi escrito.

## 3. A estreia

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 07? Em qual coluna o ganho aparece mais? |
| A subida | Até onde cada versão aguentou? |
| A velocidade de cada endpoint | Qual endpoint ficou mais rápido? Algum não mudou? Por quê? |
| O pico: o sistema | A fila de compras e a sala de espera: o que mudou? |

👉 **Observe também:** no `docker compose stats`, a CPU e a memória de cada backend, comparadas com as da 07. Agora, quem chega primeiro no limite?

Pergunta: *"se o gargalo fosse o gateway de pagamento ou o sistema do cinema, trocar de linguagem ajudaria?"*

## 4. Vale a pena reescrever?

Para discutir:

- Quanto tempo levaria reescrever um sistema de verdade? Quem mantém o código depois?
- Em qual etapa do curso trocar de linguagem teria ajudado menos? E em qual teria ajudado mais?
- Se o ganho fosse de hardware, quantas máquinas a mais o Python precisaria para empatar? Quanto isso custa por mês (lembre da conta da AWS)?

---

## Para fechar

Pergunta final: *"o que mudou mais o Ingressa: as decisões de arquitetura (etapas 02 a 06), o hardware (07) ou a linguagem (08)?"*

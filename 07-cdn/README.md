# Aula 07: A borda (CDN)

> **Objetivo:** mostrar que a requisição mais barata é a que nem chega na
> aplicação. Como numa CDN, o Nginx passa a responder sozinho o que é igual
> para todo mundo, e confere o passe da sala sem perguntar ao Python.

```
            ┌───────────────────────┐   senha   ┌──────────────────────┐
 usuário ──▶│  Sala de espera       │──────────▶│ Porteiro (no worker) │
            │  POST /sala           │◀──────────│ libera N senhas/s    │
            │  GET /sala/{senha}    │   passe   └──────────────────────┘
            └───────────┬───────────┘
                        │ com o passe (X-Passe)
                        ▼
            ┌──────────────────────────┐         ┌──────────────────────┐
            │ Nginx · a borda          │────────▶│ Ingressa (2 backends)│──▶ fila ──▶ worker
            │ confere o passe (njs)    │ só o que│ compra e sala        │
            │ programação e mapa: 1 s  │ não está└──────────────────────┘
            └──────────────────────────┘ na borda
```

O orçamento é o mesmo da etapa 06: 2 CPUs e 2 GB. Nenhuma peça nova: o Nginx que já estava na porta passou a fazer mais.

**[🖊️ Abrir o diagrama desta etapa no Excalidraw](https://excalidraw.com/#url=https://raw.githubusercontent.com/unir-dacc/system-design-web-curso/main/07-cdn/arquitetura.excalidraw)**,
para desenhar por cima durante a aula. A peça nova da etapa está em amarelo.

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`07-cdn/`).

```bash
docker compose down -v          # garante que começa do zero
docker compose up -d --build --wait
```

Rode a estreia das etapas anteriores antes da aula: o relatório desta etapa compara com o último resultado delas.

> **A estreia desta etapa é maior:** o dobro do pico da etapa 06. Com o pico de sempre, a subida
> para antes do limite da 06, e nenhuma melhora apareceria no topo do relatório.

---

## 1. Onde a 06 parou

Abra `../06-sala-de-espera/relatorios/estreia.html`.

Pergunta para a turma: *"quem já passou pela sala abre a programação e o mapa. Essas respostas mudam de uma pessoa para outra?"*

Pergunta: *"quem responde essas páginas hoje? Quanto isso custa da CPU dos backends?"*

## 2. O que mudou

| Arquivo | O que mostrar |
|---------|---------------|
| `nginx/templates/ingressa.conf.template` | O `proxy_cache`: a programação e o mapa guardados por 1 segundo. O que fazem o `proxy_cache_lock` e o `use_stale updating`? |
| `nginx/njs/passe.js` | A mesma conta do `app/sala.py`, em JavaScript, dentro do Nginx |
| `nginx/nginx.conf` | O módulo `njs` e o segredo da sala |
| `docker-compose.yml` | O ritmo do porteiro (`LIBERAR_POR_SEGUNDO`) e a estreia maior (`USUARIOS`) |

Pergunta: *"1 segundo de cache parece pouco. Com centenas de visitas por segundo, quantas chegam no backend?"*

Pergunta: *"por que o Nginx precisa conferir o passe antes de olhar o cache?"*

Pergunta: *"o código do Ingressa mudou?"*

## 3. A borda funcionando

```bash
curl -s -X POST localhost:8000/admin/reset > /dev/null
curl -s -o /dev/null -w "sem passe: %{http_code}\n" localhost:8000/filmes

curl -s -X POST localhost:8000/sala; echo           # pega uma senha
curl -s localhost:8000/sala/1; echo                 # pergunta a vez (repita até liberar)

# use o passe que veio na resposta, e repita algumas vezes
curl -s -o /dev/null -D - -H 'X-Passe: <cole o passe aqui>' localhost:8000/filmes | grep -i x-cache
```

👉 **Observe:** o cabeçalho `X-Cache`. Quando aparece `MISS` e quando aparece `HIT`? Quem respondeu em cada caso?

Agora tente um passe inventado:

```bash
curl -s -o /dev/null -w "passe falso: %{http_code}\n" -H 'X-Passe: 1.0000000000000000' localhost:8000/filmes
docker compose logs ingressa --since 1m | tail
```

👉 **Observe:** o backend ficou sabendo dessa tentativa?

## 4. A estreia

Num terminal deixe `docker compose stats`, no outro rode o teste e abra o painel em http://localhost:5665:

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

| Bloco | Perguntas |
|-------|-----------|
| O ganho de cada etapa | O que mudou em relação à 06? Em qual coluna? |
| A progressão | Em qual degrau o Ingressa deixa de ser viável? Qual meta quebrou primeiro? |
| A velocidade de cada endpoint | As páginas ficaram mais rápidas? E a sala e a compra? |
| A fila de compras | Quantas compras ficaram esperando o worker no fim? |

👉 **Observe também:** no `docker compose stats`, a CPU do Nginx e a dos backends. Quem trabalha mais agora?

## 5. A borda sozinha não basta

Volte o porteiro ao ritmo da etapa 06 e rode de novo:

```bash
LIBERAR_POR_SEGUNDO=60 docker compose up -d worker
docker compose run --rm --service-ports k6 run /scripts/estreia.js
docker compose up -d worker                              # volta ao padrão desta etapa
```

👉 **Observe:** as páginas continuam rápidas? E a espera na sala?

Pergunta: *"a borda liberou CPU dos backends. O que precisa mudar para essa CPU virar mais gente atendida?"*

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

Pergunta: *"o banco trabalhou mais ou menos que na etapa 06? Por quê?"*

---

## Para fechar a aula

Deixe no quadro as perguntas que a turma levantou:

- Uma CDN de verdade fica espalhada pelo mundo, perto de quem acessa. O que muda quando a borda está longe do backend?
- O que não pode ir para a borda? Por quê?
- O porteiro ainda tem um ritmo fixo. Quem deveria decidir esse número?

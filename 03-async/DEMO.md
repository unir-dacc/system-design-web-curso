# Aula 03: Async

> **Objetivo:** trocar o código síncrono por `async/await` com o mesmo hardware
> e descobrir o que isso muda, e o que não muda.

```
                 SÍNCRONO (aulas 01 e 02)                        ASYNC (esta aula)

  requisição ─▶ [thread 1] espera o cinema...          requisição ─▶ ┐
  requisição ─▶ [thread 2] espera o gateway...         requisição ─▶ ├─▶ [event loop] enquanto uma espera,
  ...                                                  requisição ─▶ │                 atende as outras
  requisição ─▶ [thread 40] espera...                  ...           ┘
  requisição ─▶ fila: espera uma thread livre
```

## 0. Preparação (antes da aula)

Todos os comandos são rodados **dentro desta pasta** (`03-async/`).

```bash
(cd ../02-cache && docker compose down -v)   # derruba a etapa anterior
docker compose down -v
docker compose up -d --build --wait
```

Deixe à mão o relatório da aula 02 (`../02-cache/relatorios/estreia.html`) para comparar.

---

## 1. O que o relatório da aula 02 deixou no ar

Abra o relatório da 02 na tabela da subida e olhe a coluna do mapa nos degraus acima do limite.

Pergunta para a turma: *"o mapa estava no cache, que responde em milissegundos. Por que ele demorou tanto?"*

Pista: o comentário no topo de `../02-cache/app/routes/catalogo.py`.

## 2. O que mudou no código

```bash
git diff --no-index ../02-cache/app app
```

| Arquivo | O que mostrar |
|---------|---------------|
| `app/routes/*.py` | `def` virou `async def`, e cada espera ganhou um `await` |
| `app/db.py` | O banco async (`asyncpg`). O limite agora é o pool de conexões, não as threads |
| `app/clients.py` e `app/cache.py` | Cinema, gateway e Redis com clientes async |
| `app/routes/catalogo.py` | A rota do mapa devolve a conexão do banco **antes** de esperar o cache |
| `app/compra.py` | A compra responde na hora (202): o pagamento, a confirmação e o e-mail continuam em segundo plano (`asyncio.create_task`); o e-mail e o QR code rodam numa thread |
| `app/routes/pedidos.py` | O cliente acompanha o pedido em `GET /pedidos/{id}` até ser confirmado ou recusado |
| `app/models.py` | `lazy="selectin"`: no async, não dá para carregar relacionamentos "escondidos" |

Pergunta: *"por que o e-mail e o QR code vão para uma thread, se agora tudo é async? O que aconteceria com as outras requisições enquanto o QR code é gerado?"*

Pergunta: *"o pagamento agora acontece depois da resposta. O que acontece com ele se o processo do Ingressa cair nesse meio-tempo?"*

## 3. A estreia

```bash
docker compose run --rm --service-ports k6 run /scripts/estreia.js
xdg-open relatorios/estreia.html
```

Abra o relatório desta aula ao lado do relatório da aula 02.

| Bloco | Perguntas |
|-------|-----------|
| Topo | O máximo que o Ingressa aguenta mudou? Por quê? |
| A subida | Nos degraus acima do limite, o que aconteceu com o tempo do mapa? |
| O pico | O Ingressa travou desta vez? Quantos ingressos foram vendidos na rodada? |

Pergunta: *"o async deixou o Ingressa mais rápido? Ou deixou ele esperar melhor?"*

## 4. Um limite novo

Depois da estreia, procure nos logs:

```bash
docker compose logs ingressa | grep -c "Too many open files"
docker compose exec ingressa sh -c 'ulimit -n'
```

👉 **Observe:** a mensagem e o limite de arquivos abertos do processo.

Pergunta: *"o que é um arquivo aberto, para um servidor web? Por que esse erro não aparecia nas aulas 01 e 02?"*

---

## Para fechar a aula

- O async aumentou a capacidade? O que ele mudou de verdade?
- Quem continua limitando as compras?
- Aceitar todo mundo que chega é sempre bom?

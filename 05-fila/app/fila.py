"""
Fila de compras (Redis).

A requisição de compra só reserva os assentos e põe uma tarefa aqui; o worker
(app/worker.py) tira as tarefas da fila e conclui as compras: cobra, confirma
no cinema, emite os ingressos e manda o e-mail.

A fila vive no Redis, fora dos processos: se um backend cair, as compras que
ele aceitou continuam na fila. E se o worker cair no meio de uma compra?
Ao pegar uma tarefa, o worker a move para a lista "processando" (num único
comando, sem chance de perdê-la no meio do caminho). Só quando termina ele a
apaga de lá. Ao subir de novo, o que ficou em "processando" volta para a fila.
"""

import json

from app.cache import r

FILA = "fila:compras"
PROCESSANDO = "fila:compras:processando"


def enfileirar(tarefa: dict) -> None:
    r.lpush(FILA, json.dumps(tarefa))


def proxima(espera_s: int = 5) -> bytes | None:
    """Pega a próxima tarefa (a mais antiga), esperando até `espera_s` segundos se a fila estiver vazia."""
    return r.blmove(FILA, PROCESSANDO, espera_s, "RIGHT", "LEFT")


def terminar(tarefa: bytes) -> None:
    r.lrem(PROCESSANDO, 1, tarefa)


def recuperar() -> int:
    """Devolve para a fila as tarefas que ficaram pela metade. Só funciona com um worker."""
    devolvidas = 0
    while r.lmove(PROCESSANDO, FILA, "RIGHT", "RIGHT") is not None:
        devolvidas += 1
    return devolvidas


def tamanho() -> int:
    """Compras ainda não concluídas: as que esperam o worker e as que ele está fazendo."""
    return r.llen(FILA) + r.llen(PROCESSANDO)

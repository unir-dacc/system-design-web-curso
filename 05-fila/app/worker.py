"""
Worker: tira as compras da fila e conclui cada uma (app/compra.py).

Roda num container separado dos backends, com o mesmo código. Cada compra
passa a maior parte do tempo esperando o gateway de pagamento, então o worker
trabalha em várias ao mesmo tempo, uma por thread.

    python -m app.worker
"""

import json
import logging
import os
import threading

from app import compra, fila

THREADS = int(os.getenv("WORKER_THREADS", "40"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")
# Sem uma linha de log para cada chamada ao gateway e ao cinema
logging.getLogger("httpx").setLevel(logging.WARNING)


def trabalhar() -> None:
    while True:
        tarefa = fila.proxima()  # espera até chegar uma
        if tarefa is None:
            continue
        try:
            compra.concluir_compra(**json.loads(tarefa))
        except Exception:
            # Não volta para a fila: uma tarefa com defeito travaria o worker para sempre
            log.exception("Falha ao concluir a tarefa %s", tarefa)
        finally:
            fila.terminar(tarefa)


def main() -> None:
    devolvidas = fila.recuperar()
    if devolvidas:
        log.info("%s compras ficaram pela metade e voltaram para a fila", devolvidas)
    log.info("Worker pronto: %s threads, %s compras na fila", THREADS, fila.tamanho())
    trabalhadores = [threading.Thread(target=trabalhar, daemon=True) for _ in range(THREADS)]
    for t in trabalhadores:
        t.start()
    for t in trabalhadores:
        t.join()


if __name__ == "__main__":
    main()

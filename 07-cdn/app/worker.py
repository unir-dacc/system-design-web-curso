"""
Worker: tira as compras da fila e conclui cada uma (app/compra.py). Também
roda o porteiro da sala de espera (app/sala.py).

Roda num container separado dos backends, com o mesmo código. Cada compra
passa a maior parte do tempo esperando o gateway de pagamento, então o worker
trabalha em várias ao mesmo tempo, uma por thread.

    python -m app.worker
"""

import json
import logging
import os
import threading
import time

from app import compra, fila, sala

THREADS = int(os.getenv("WORKER_THREADS", "40"))
# Quantas pessoas da sala de espera entram por segundo: um pouco abaixo do que
# o Ingressa aguenta
LIBERAR_POR_SEGUNDO = int(os.getenv("LIBERAR_POR_SEGUNDO", "60"))

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


def porteiro() -> None:
    """Libera senhas da sala de espera num ritmo fixo, um pouco a cada 0,2 s."""
    while True:
        try:
            sala.anotar_taxa(LIBERAR_POR_SEGUNDO)  # de novo a cada volta: o reset das aulas apaga o Redis
            sala.liberar(max(1, round(LIBERAR_POR_SEGUNDO * 0.2)))
        except Exception:
            log.exception("Falha no porteiro da sala de espera")
        time.sleep(0.2)


def main() -> None:
    devolvidas = fila.recuperar()
    if devolvidas:
        log.info("%s compras ficaram pela metade e voltaram para a fila", devolvidas)
    log.info("Worker pronto: %s threads, %s compras na fila", THREADS, fila.tamanho())
    log.info("Porteiro da sala de espera: %s pessoas por segundo", LIBERAR_POR_SEGUNDO)
    trabalhadores = [threading.Thread(target=trabalhar, daemon=True) for _ in range(THREADS)]
    trabalhadores.append(threading.Thread(target=porteiro, daemon=True))
    for t in trabalhadores:
        t.start()
    for t in trabalhadores:
        t.join()


if __name__ == "__main__":
    main()

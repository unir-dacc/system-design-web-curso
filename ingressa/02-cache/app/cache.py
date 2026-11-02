"""
Cache de respostas prontas (Redis).

A programação e o mapa de assentos são iguais para todo mundo. Em vez de
montar a mesma resposta para cada usuário (consultar o banco ou o cinema,
converter para JSON...), o Ingressa monta uma vez, guarda o JSON pronto no
Redis e entrega a cópia para os próximos.

Cada resposta tem um prazo de validade (TTL). Quando algo muda (uma compra
reserva ou libera assentos), o Ingressa apaga a cópia daquela sessão na hora,
e a próxima visita monta uma nova.

Proteção contra estouro de cache (cache stampede): quando a cópia não existe,
só UMA requisição monta a resposta; as outras esperam ela ficar pronta. Sem
isso, todas as visitas daquele instante iriam juntas ao banco ou ao cinema.
"""

import time
from collections.abc import Callable

import redis

from app.config import REDIS_URL

r = redis.Redis.from_url(REDIS_URL)

TRAVA_S = 10  # se quem está montando a resposta travar, a trava se desfaz sozinha
ESPERA_MAXIMA_S = 5


def resposta_pronta(chave: str, validade_s: int, montar: Callable[[], bytes]) -> bytes:
    """Devolve a resposta guardada em `chave` ou, se não houver, monta, guarda e devolve."""
    guardada = r.get(chave)
    if guardada is not None:
        return guardada

    # Só quem conseguir criar a trava monta a resposta
    if r.set(f"trava:{chave}", 1, nx=True, ex=TRAVA_S):
        try:
            resposta = montar()
            r.set(chave, resposta, ex=validade_s)
            return resposta
        finally:
            r.delete(f"trava:{chave}")

    # Outra requisição já está montando: espera a cópia aparecer
    limite = time.time() + ESPERA_MAXIMA_S
    while time.time() < limite:
        time.sleep(0.02)
        guardada = r.get(chave)
        if guardada is not None:
            return guardada
    return montar()


def chave_do_mapa(sessao_id: int) -> str:
    return f"mapa:{sessao_id}"


def esquecer(chave: str) -> None:
    r.delete(chave)


def limpar() -> None:
    r.flushdb()

"""
Cache de respostas prontas (Redis), igual ao das outras etapas: a programação
e o mapa de assentos são iguais para todo mundo. O Ingressa monta uma vez,
guarda o JSON pronto e entrega a cópia para os próximos.

Proteção contra estouro de cache: quando a cópia não existe, só UMA
requisição monta a resposta; as outras esperam ela ficar pronta.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as redis

from app.config import REDIS_URL

# O cliente usa o hiredis (em C) para ler as respostas do Redis. Com as 100
# conexões em uso, a próxima requisição espera uma ficar livre (o pool padrão
# do redis-py daria erro na hora)
r: Any = redis.Redis(connection_pool=redis.BlockingConnectionPool.from_url(REDIS_URL, max_connections=100, timeout=None))

TRAVA_S = 10  # se quem está montando travar, a trava se desfaz sozinha
ESPERA_MAXIMA_S = 5.0
INTERVALO_ESPERA_S = 0.02


async def resposta_pronta(chave: str, validade_s: int, montar: Callable[[], Awaitable[bytes]]) -> bytes:
    """Devolve a resposta guardada em `chave` ou, se não houver, monta, guarda e devolve."""
    guardada = await r.get(chave)
    if guardada is not None:
        return guardada

    # Só quem conseguir criar a trava monta a resposta
    # (sem try/finally: o mypyc 1.18 erra ao repassar uma exceção de dentro dele)
    if await r.set("trava:" + chave, 1, nx=True, ex=TRAVA_S):
        try:
            resposta = await montar()
        except Exception:
            await r.delete("trava:" + chave)
            raise
        await r.set(chave, resposta, ex=validade_s)
        await r.delete("trava:" + chave)
        return resposta

    # Outra requisição já está montando: espera a cópia aparecer
    limite = time.monotonic() + ESPERA_MAXIMA_S
    while time.monotonic() < limite:
        await asyncio.sleep(INTERVALO_ESPERA_S)
        guardada = await r.get(chave)
        if guardada is not None:
            return guardada
    return await montar()


def chave_do_mapa(sessao_id: int) -> str:
    return f"mapa:{sessao_id}"


async def mapa_mudou(sessao_id: int) -> None:
    """Os assentos da sessão mudaram: a cópia do mapa no cache ficou velha."""
    await r.delete(chave_do_mapa(sessao_id))

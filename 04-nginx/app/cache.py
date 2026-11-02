"""
Cache do mapa de assentos (padrão cache-aside).

1. Procura o mapa no Redis.
2. Se não achar, busca no sistema do cinema e guarda por MAPA_TTL_S segundos.

Durante esse tempo, quem abrir o mapa da mesma sessão recebe a cópia guardada,
sem ocupar o sistema do cinema. A cópia pode estar alguns segundos atrasada:
se alguém escolher um assento que acabou de ser vendido, a reserva no cinema
recusa (409), como antes.
"""

import json

import redis.asyncio as redis

from app import clients
from app.config import MAPA_TTL_S, REDIS_URL

r = redis.Redis.from_url(REDIS_URL)


async def mapa_de_assentos(sessao_id: int) -> list[dict]:
    chave = f"mapa:{sessao_id}"

    guardado = await r.get(chave)
    if guardado is not None:
        return json.loads(guardado)

    assentos = await clients.buscar_mapa(sessao_id)
    await r.set(chave, json.dumps(assentos), ex=MAPA_TTL_S)
    return assentos


async def limpar() -> None:
    await r.flushdb()

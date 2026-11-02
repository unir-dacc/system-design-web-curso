"""
Cache do mapa de assentos.

O mapa de cada sessão fica guardado no Redis junto com a hora em que foi
buscado no sistema do cinema:

- Cópia recente (até MAPA_TTL_S segundos): devolve direto.
- Cópia velha: UMA requisição ganha a trava e busca um mapa novo no cinema;
  as outras devolvem a cópia velha na hora, sem ir ao cinema.
- Nenhuma cópia (o primeiro acesso): quem ganha a trava busca no cinema;
  as outras esperam a cópia aparecer.

Assim o cinema recebe no máximo uma busca por sessão a cada MAPA_TTL_S
segundos, não importa quantas pessoas abram o mapa ao mesmo tempo. Sem isso,
quando a cópia expira, todas as requisições daquele instante iriam juntas ao
cinema ("estouro de cache", ou cache stampede).

A cópia pode estar alguns segundos atrasada: se alguém escolher um assento que
acabou de ser vendido, a reserva no cinema recusa (409).
"""

import json
import time

import redis

from app import clients
from app.config import MAPA_TTL_S, REDIS_URL

r = redis.Redis.from_url(REDIS_URL)

GUARDAR_POR_S = 300  # a cópia velha continua disponível bem depois de vencer
TRAVA_S = 10  # se quem está buscando travar, a trava se desfaz sozinha
ESPERA_MAXIMA_S = 10


def mapa_de_assentos(sessao_id: int) -> list[dict]:
    chave = f"mapa:{sessao_id}"
    guardado = ler(chave)

    if guardado and time.time() - guardado["buscado_em"] < MAPA_TTL_S:
        return guardado["assentos"]

    # Só quem conseguir criar a trava vai ao cinema
    if r.set(f"trava:{chave}", 1, nx=True, ex=TRAVA_S):
        try:
            return buscar_e_guardar(sessao_id, chave)
        finally:
            r.delete(f"trava:{chave}")

    # Outra requisição já está buscando
    if guardado:
        return guardado["assentos"]

    limite = time.time() + ESPERA_MAXIMA_S
    while time.time() < limite:
        time.sleep(0.05)
        guardado = ler(chave)
        if guardado:
            return guardado["assentos"]
    return buscar_e_guardar(sessao_id, chave)


def ler(chave: str) -> dict | None:
    guardado = r.get(chave)
    return json.loads(guardado) if guardado is not None else None


def buscar_e_guardar(sessao_id: int, chave: str) -> list[dict]:
    assentos = clients.buscar_mapa(sessao_id)
    r.set(chave, json.dumps({"buscado_em": time.time(), "assentos": assentos}), ex=GUARDAR_POR_S)
    return assentos


def limpar() -> None:
    r.flushdb()

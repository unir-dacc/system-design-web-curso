"""
Estado dos assentos no Ingressa (Redis).

O sistema do cinema continua sendo o dono dos assentos, mas cada atendimento
dele é caro. Para não gastá-lo à toa, o Ingressa guarda o que ele mesmo já
sabe sobre cada sessão:

- travados: assentos de pedidos em andamento (com o dono e um prazo)
- vendidos: assentos de pedidos confirmados

Antes de pedir uma reserva ao cinema, a compra trava os assentos aqui. Se
algum já estiver travado ou vendido, a resposta é imediata, sem ir ao cinema.
O mapa também usa essas informações, então os usuários quase não escolhem
assentos que já foram pegos, mesmo com a cópia do cinema alguns segundos
atrasada.
"""

import time

from app.cache import r

TRAVA_S = 120  # se o processo cair no meio da compra, a trava se desfaz sozinha


def _chaves(sessao_id: int) -> list[str]:
    return [f"assentos:{sessao_id}:travados", f"assentos:{sessao_id}:vendidos"]


# Trava todos os assentos do pedido, ou nenhum. Devolve a lista dos que já
# estavam travados ou vendidos (vazia = conseguiu). Roda dentro do Redis, de
# uma vez só (atômico). Cada trava guarda "dono|prazo".
_travar = r.register_script(
    """
    local agora = tonumber(ARGV[1])
    local prazo = agora + tonumber(ARGV[2])
    local dono = ARGV[3]
    local ocupados = {}
    for i = 4, #ARGV do
        local assento = ARGV[i]
        local trava = redis.call('HGET', KEYS[1], assento)
        local travado = trava and tonumber(string.match(trava, '|(.+)$')) > agora
        if travado or redis.call('SISMEMBER', KEYS[2], assento) == 1 then
            table.insert(ocupados, assento)
        end
    end
    if #ocupados == 0 then
        for i = 4, #ARGV do
            redis.call('HSET', KEYS[1], ARGV[i], dono .. '|' .. prazo)
        end
    end
    return ocupados
    """
)

# Solta as travas de um dono (e só dele)
_soltar = r.register_script(
    """
    for i = 2, #ARGV do
        local trava = redis.call('HGET', KEYS[1], ARGV[i])
        if trava and string.match(trava, '^(.-)|') == ARGV[1] then
            redis.call('HDEL', KEYS[1], ARGV[i])
        end
    end
    """
)


def travar(sessao_id: int, assentos: list[str], dono: str) -> list[str]:
    """Trava os assentos para o pedido. Devolve os que já estavam ocupados (vazia = conseguiu)."""
    ocupados = _travar(keys=_chaves(sessao_id), args=[time.time(), TRAVA_S, dono, *assentos])
    return [a.decode() if isinstance(a, bytes) else a for a in ocupados]


def soltar(sessao_id: int, assentos: list[str], dono: str) -> None:
    _soltar(keys=_chaves(sessao_id)[:1], args=[dono, *assentos])


def marcar_vendidos(sessao_id: int, assentos: list[str], dono: str) -> None:
    _, vendidos = _chaves(sessao_id)
    r.sadd(vendidos, *assentos)
    soltar(sessao_id, assentos, dono)


def aplicar_ao_mapa(sessao_id: int, mapa: list[dict]) -> list[dict]:
    """Junta a cópia do mapa do cinema com o que o Ingressa já sabe."""
    travados, vendidos = _chaves(sessao_id)
    agora = time.time()
    em_andamento = {
        assento.decode(): trava.decode()
        for assento, trava in r.hgetall(travados).items()
    }
    ja_vendidos = {a.decode() for a in r.smembers(vendidos)}

    resultado = []
    for assento in mapa:
        codigo, status = assento["codigo"], assento["status"]
        if codigo in ja_vendidos:
            status = "vendido"
        elif codigo in em_andamento and float(em_andamento[codigo].split("|")[1]) > agora:
            status = "reservado"
        resultado.append({"codigo": codigo, "status": status})
    return resultado

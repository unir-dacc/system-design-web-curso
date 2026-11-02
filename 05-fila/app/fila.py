"""
Fila virtual (sala de espera).

Quem chega pega uma senha. Um liberador avança, no ritmo que o sistema
aguenta (RITMO_FILA_POR_S), o número da última senha liberada. A posição de
cada pessoa é só a diferença entre a senha dela e a última liberada: não
existe uma lista de pessoas na memória, só dois contadores no Redis.

Quem é liberado ganha uma janela de JANELA_COMPRA_S segundos para comprar.
Uma senha vale uma compra.

Quem desiste da fila simplesmente para de consultar a posição. Cada consulta
renova um "sinal de vida" da senha; o liberador pula as senhas sem sinal de
vida, para não gastar com elas uma vaga do ritmo.
"""

import asyncio
import time

from app.cache import r
from app.config import JANELA_COMPRA_S, RITMO_FILA_POR_S

EMITIDAS = "fila:emitidas"
LIBERADAS = "fila:liberadas"
SINAL_DE_VIDA_S = 30  # maior que o maior intervalo entre consultas (15 s)

# Libera a próxima senha de alguém que ainda está esperando, pulando as senhas
# abandonadas (sem sinal de vida). Nunca passa da última emitida: se não há
# ninguém esperando, a capacidade daquele momento não fica "guardada" para depois.
# Roda dentro do Redis, de uma vez só (atômico).
_liberar_uma = r.register_script(
    """
    local emitidas = tonumber(redis.call('GET', KEYS[1]) or '0')
    local liberadas = tonumber(redis.call('GET', KEYS[2]) or '0')
    local pulos = 0
    while liberadas < emitidas and pulos < 1000 do
        liberadas = liberadas + 1
        if redis.call('EXISTS', 'fila:viva:' .. liberadas) == 1 then
            break
        end
        pulos = pulos + 1
    end
    redis.call('SET', KEYS[2], liberadas)
    """
)


async def liberador() -> None:
    """Roda para sempre, em segundo plano, liberando RITMO_FILA_POR_S senhas por segundo."""
    while True:
        await _liberar_uma(keys=[EMITIDAS, LIBERADAS])
        await asyncio.sleep(1 / RITMO_FILA_POR_S)


async def entrar() -> dict:
    senha = await r.incr(EMITIDAS)
    await r.set(f"fila:viva:{senha}", 1, ex=SINAL_DE_VIDA_S)
    return await consultar(senha)


async def consultar(senha: int) -> dict | None:
    emitidas = int(await r.get(EMITIDAS) or 0)
    if senha < 1 or senha > emitidas:
        return None
    liberadas = int(await r.get(LIBERADAS) or 0)

    if senha > liberadas:
        await r.set(f"fila:viva:{senha}", 1, ex=SINAL_DE_VIDA_S)  # ainda estou aqui
        posicao = senha - liberadas
        estimativa_s = posicao / RITMO_FILA_POR_S
        return {
            "senha": senha,
            "liberado": False,
            "posicao": posicao,
            "estimativa_s": round(estimativa_s),
            # Quem está longe consulta menos vezes: milhares de pessoas perguntando
            # "e agora?" a cada segundo também seriam uma sobrecarga
            "consultar_em_s": min(15, max(2, round(estimativa_s / 10))),
        }

    # Liberada: a janela para comprar começa na primeira consulta depois da liberação
    chave = f"fila:janela:{senha}"
    await r.set(chave, time.time() + JANELA_COMPRA_S, nx=True, ex=24 * 3600)
    valida_ate = float(await r.get(chave))
    return {
        "senha": senha,
        "liberado": valida_ate > time.time(),
        "posicao": 0,
        "valida_por_s": max(0, round(valida_ate - time.time())),
    }


async def senha_valida(senha: int) -> bool:
    valida_ate = await r.get(f"fila:janela:{senha}")
    return valida_ate is not None and float(valida_ate) > time.time()


async def usar(senha: int) -> None:
    """Depois de uma compra concluída, a senha não vale mais."""
    await r.set(f"fila:janela:{senha}", 0, xx=True)


async def estado() -> dict:
    emitidas = int(await r.get(EMITIDAS) or 0)
    liberadas = int(await r.get(LIBERADAS) or 0)
    return {
        "senhas_emitidas": emitidas,
        "senhas_liberadas": liberadas,
        "pessoas_esperando": emitidas - liberadas,
        "ritmo_por_s": RITMO_FILA_POR_S,
    }

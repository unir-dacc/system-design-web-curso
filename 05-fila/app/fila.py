"""
Fila virtual (sala de espera).

Quem chega pega uma senha. A posição de cada pessoa é só a diferença entre a
senha dela e a última liberada: não existe uma lista de pessoas na memória,
só contadores no Redis.

O liberador deixa no máximo MAX_COMPRANDO pessoas comprando ao mesmo tempo.
Quando alguém termina a compra, some ou estoura a janela de JANELA_COMPRA_S
segundos, a vaga abre e a próxima senha é liberada. Assim a fila se ajusta
sozinha: se as compras andam rápido, entra mais gente; se o sistema do cinema
fica lento, entra menos.

Ninguém avisa quando desiste: a pessoa simplesmente some. Por isso:
- quem espera consulta a posição de tempos em tempos, e cada consulta renova
  um "sinal de vida"; o liberador pula as senhas sem sinal de vida;
- quem está comprando tem um prazo curto (PRAZO_COMPRANDO_S), renovado a cada
  consulta ou tentativa de compra; sem renovação, a vaga volta para a fila.
"""

import asyncio
import time

from app.cache import r
from app.config import JANELA_COMPRA_S, MAX_COMPRANDO

EMITIDAS = "fila:emitidas"
LIBERADAS = "fila:liberadas"
COMPRANDO = "fila:comprando"  # senhas comprando agora, com o prazo de cada uma

# Quanto tempo falta para chegar à frente, estimado por quantas compras cabem
# por segundo (cada pessoa leva uns 4 s comprando).
SEGUNDOS_POR_COMPRA = 4
# Quem está longe consulta pouco: milhares de pessoas perguntando "e agora?" o
# tempo todo derrubariam o próprio Ingressa. Mas o intervalo diminui conforme a
# pessoa se aproxima da frente, para ninguém ser liberado enquanto "dorme".
CONSULTAR_NO_MAXIMO_A_CADA_S = 20
SINAL_DE_VIDA_S = 45  # maior que o maior intervalo de consulta
PRAZO_COMPRANDO_S = 10
PRAZO_PARA_SE_APRESENTAR_S = 3  # liberado e não apareceu: a vaga volta logo

# Libera senhas enquanto houver vaga para comprar, pulando as abandonadas.
# Roda dentro do Redis, de uma vez só (atômico).
_liberar = r.register_script(
    """
    local agora = tonumber(ARGV[1])
    local maximo = tonumber(ARGV[2])
    local prazo_inicial = tonumber(ARGV[3])

    -- devolvem a vaga: quem terminou o prazo sem dar sinal
    redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', agora)

    local emitidas = tonumber(redis.call('GET', KEYS[1]) or '0')
    local liberadas = tonumber(redis.call('GET', KEYS[2]) or '0')
    local pulos = 0
    while redis.call('ZCARD', KEYS[3]) < maximo and liberadas < emitidas and pulos < 1000 do
        liberadas = liberadas + 1
        if redis.call('EXISTS', 'fila:viva:' .. liberadas) == 1 then
            redis.call('ZADD', KEYS[3], agora + prazo_inicial, liberadas)
        else
            pulos = pulos + 1
        end
    end
    redis.call('SET', KEYS[2], liberadas)
    """
)


async def liberador() -> None:
    """Roda para sempre, em segundo plano, abrindo vagas conforme as compras terminam."""
    while True:
        await _liberar(keys=[EMITIDAS, LIBERADAS, COMPRANDO], args=[time.time(), MAX_COMPRANDO, PRAZO_PARA_SE_APRESENTAR_S])
        await asyncio.sleep(0.05)


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
        estimativa_s = posicao * SEGUNDOS_POR_COMPRA / MAX_COMPRANDO
        return {
            "senha": senha,
            "liberado": False,
            "posicao": posicao,
            "estimativa_s": round(estimativa_s),
            # Umas 4 consultas até chegar à frente: nem demais, nem de menos
            "consultar_em_s": max(1, min(CONSULTAR_NO_MAXIMO_A_CADA_S, round(estimativa_s / 4))),
        }

    if not await senha_valida(senha):
        # Já comprou, sumiu por tempo demais ou estourou a janela: precisa voltar para a fila
        return {"senha": senha, "liberado": False, "posicao": 0, "expirada": True}
    return {"senha": senha, "liberado": True, "posicao": 0}


async def senha_valida(senha: int) -> bool:
    """Confere se a senha está comprando agora e renova o prazo dela."""
    prazo = await r.zscore(COMPRANDO, senha)
    if prazo is None or prazo < time.time():
        return False
    # A janela total começa na primeira vez que a senha é usada
    await r.set(f"fila:janela:{senha}", time.time() + JANELA_COMPRA_S, nx=True, ex=JANELA_COMPRA_S * 2)
    fim_da_janela = float(await r.get(f"fila:janela:{senha}"))
    if fim_da_janela < time.time():
        await r.zrem(COMPRANDO, senha)
        return False
    await r.zadd(COMPRANDO, {senha: min(time.time() + PRAZO_COMPRANDO_S, fim_da_janela)})
    return True


async def usar(senha: int) -> None:
    """Depois de uma compra concluída, a senha não vale mais e a vaga abre para o próximo."""
    await r.zrem(COMPRANDO, senha)


async def estado() -> dict:
    emitidas = int(await r.get(EMITIDAS) or 0)
    liberadas = int(await r.get(LIBERADAS) or 0)
    return {
        "senhas_emitidas": emitidas,
        "senhas_liberadas": liberadas,
        "pessoas_esperando": emitidas - liberadas,
        "comprando_agora": await r.zcard(COMPRANDO),
        "max_comprando": MAX_COMPRANDO,
    }


async def depois_de_falhar(senha: int) -> None:
    """A compra falhou (assento ocupado, cartão recusado...): quem quiser tentar de
    novo tem PRAZO_PARA_SE_APRESENTAR_S segundos; quem desistiu devolve a vaga logo."""
    await r.zadd(COMPRANDO, {senha: time.time() + PRAZO_PARA_SE_APRESENTAR_S}, xx=True)


async def sair(senha: int) -> None:
    """A pessoa avisou que desistiu: a senha é pulada e a vaga (se tinha) abre na hora."""
    await r.delete(f"fila:viva:{senha}")
    await r.zrem(COMPRANDO, senha)

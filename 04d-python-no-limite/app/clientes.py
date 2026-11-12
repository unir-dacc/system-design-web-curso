"""
Comunicação com os sistemas externos: cinema e gateway de pagamento, com o
aiohttp (o HTTP é lido por um parser em C).
"""

from typing import Any

import aiohttp
import msgspec

from app.config import CINEMA_URL, GATEWAY_URL
from app.erros import AssentosIndisponiveis, AssentosInexistentes, PagamentoNaoRealizado
from app.modelos import Assento, mapa_do_cinema_decoder

# Preenchido por conectar(), na primeira requisição: reaproveita as conexões
sessao_http: Any = None

# ⚠️ PROPOSITAL: sem timeout para o cinema (como nas outras etapas).
SEM_TIMEOUT = aiohttp.ClientTimeout(total=None)
# A cobrança tem timeout: sem ele, um gateway travado prenderia o assento para sempre.
TIMEOUT_DO_GATEWAY = aiohttp.ClientTimeout(total=10)

CABECALHOS = {"Content-Type": "application/json"}


async def conectar() -> None:
    global sessao_http
    sessao_http = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=0), timeout=SEM_TIMEOUT)


async def _chamar(metodo: str, url: str, corpo: Any = None, cabecalhos: dict[str, str] | None = None,
                  timeout: aiohttp.ClientTimeout = SEM_TIMEOUT) -> tuple[int, bytes]:
    dados = msgspec.json.encode(corpo) if corpo is not None else None
    async with sessao_http.request(metodo, url, data=dados, headers=cabecalhos or CABECALHOS, timeout=timeout) as resposta:
        return resposta.status, await resposta.read()


def _conferir(url: str, status: int) -> None:
    if status >= 400:
        raise RuntimeError(f"{url} respondeu {status}")


# --- Sistema de assentos do cinema ---


async def buscar_mapa(sessao_id: int) -> list[Assento]:
    url = f"{CINEMA_URL}/sessoes/{sessao_id}/assentos"
    status, conteudo = await _chamar("GET", url)
    _conferir(url, status)
    mapa: Any = mapa_do_cinema_decoder.decode(conteudo)
    return mapa.assentos


async def reservar_assentos(sessao_id: int, assentos: list[str]) -> str:
    url = f"{CINEMA_URL}/sessoes/{sessao_id}/reservas"
    status, conteudo = await _chamar("POST", url, {"assentos": assentos})
    if status == 409:
        raise AssentosIndisponiveis(msgspec.json.decode(conteudo)["detail"]["indisponiveis"])
    if status == 422:
        raise AssentosInexistentes(msgspec.json.decode(conteudo)["detail"]["assentos"])
    _conferir(url, status)
    reserva_id: str = msgspec.json.decode(conteudo)["reserva_id"]
    return reserva_id


async def confirmar_reserva(reserva_id: str) -> None:
    url = f"{CINEMA_URL}/reservas/{reserva_id}/confirmar"
    status, _ = await _chamar("POST", url)
    _conferir(url, status)


async def cancelar_reserva(reserva_id: str) -> None:
    url = f"{CINEMA_URL}/reservas/{reserva_id}"
    status, _ = await _chamar("DELETE", url)
    _conferir(url, status)


# --- Gateway de pagamento ---


async def cobrar(valor_centavos: int, cartao_token: str, referencia: str) -> dict[str, Any]:
    corpo = {"valor_centavos": valor_centavos, "cartao_token": cartao_token, "referencia": referencia}
    # Se a mesma cobrança for enviada de novo, o gateway não cobra duas vezes
    cabecalhos = {"Content-Type": "application/json", "Idempotency-Key": referencia}
    try:
        status, conteudo = await _chamar("POST", f"{GATEWAY_URL}/cobrancas", corpo, cabecalhos, TIMEOUT_DO_GATEWAY)
        if status < 400:
            cobranca: dict[str, Any] = msgspec.json.decode(conteudo)
            return cobranca
    except (aiohttp.ClientError, TimeoutError):
        pass
    # Erro ou timeout: a cobrança pode ter acontecido ou não.
    # Antes de liberar o assento, pergunta ao gateway.
    existente = await buscar_cobranca(referencia)
    if existente is None:
        raise PagamentoNaoRealizado()
    return existente


async def buscar_cobranca(referencia: str) -> dict[str, Any] | None:
    url = f"{GATEWAY_URL}/cobrancas?referencia={referencia}"
    status, conteudo = await _chamar("GET", url, timeout=TIMEOUT_DO_GATEWAY)
    _conferir(url, status)
    cobrancas: list[dict[str, Any]] = msgspec.json.decode(conteudo)
    return cobrancas[0] if cobrancas else None

"""Comunicação com os sistemas externos: cinema e gateway de pagamento."""

import httpx

from app.config import CINEMA_URL, GATEWAY_URL

# Enquanto espera a resposta de um sistema externo, o Ingressa fica livre
# para atender outras requisições: é isso que o "await" faz.
# ⚠️ PROPOSITAL: sem timeout. Se um sistema externo travar, a requisição do
# cliente trava junto.
http = httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=None))


class AssentosIndisponiveis(Exception):
    def __init__(self, assentos: list[str]):
        super().__init__(f"Assentos indisponíveis: {', '.join(assentos)}")
        self.assentos = assentos


class AssentosInexistentes(Exception):
    def __init__(self, assentos: list[str]):
        super().__init__(f"Assentos inexistentes: {', '.join(assentos)}")
        self.assentos = assentos


# --- Sistema de assentos do cinema ---


async def buscar_mapa(sessao_id: int) -> list[dict]:
    resposta = await http.get(f"{CINEMA_URL}/sessoes/{sessao_id}/assentos")
    resposta.raise_for_status()
    return resposta.json()["assentos"]


async def reservar_assentos(sessao_id: int, assentos: list[str]) -> str:
    resposta = await http.post(f"{CINEMA_URL}/sessoes/{sessao_id}/reservas", json={"assentos": assentos})
    if resposta.status_code == 409:
        raise AssentosIndisponiveis(resposta.json()["detail"]["indisponiveis"])
    if resposta.status_code == 422:
        raise AssentosInexistentes(resposta.json()["detail"]["assentos"])
    resposta.raise_for_status()
    return resposta.json()["reserva_id"]


async def confirmar_reserva(reserva_id: str) -> None:
    (await http.post(f"{CINEMA_URL}/reservas/{reserva_id}/confirmar")).raise_for_status()


async def cancelar_reserva(reserva_id: str) -> None:
    (await http.delete(f"{CINEMA_URL}/reservas/{reserva_id}")).raise_for_status()


# --- Gateway de pagamento ---


async def cobrar(valor_centavos: int, cartao_token: str, referencia: str) -> dict:
    resposta = await http.post(
        f"{GATEWAY_URL}/cobrancas",
        json={"valor_centavos": valor_centavos, "cartao_token": cartao_token, "referencia": referencia},
    )
    resposta.raise_for_status()
    return resposta.json()

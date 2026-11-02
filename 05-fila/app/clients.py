"""Comunicação com os sistemas externos: cinema e gateway de pagamento."""

import httpx

from app.config import CINEMA_URL, GATEWAY_URL

# ⚠️ PROPOSITAL: sem timeout. Se um sistema externo travar,
# a requisição do cliente trava junto, e segura uma thread e uma conexão do banco.
http = httpx.Client(timeout=None)


class AssentosIndisponiveis(Exception):
    def __init__(self, assentos: list[str]):
        super().__init__(f"Assentos indisponíveis: {', '.join(assentos)}")
        self.assentos = assentos


class AssentosInexistentes(Exception):
    def __init__(self, assentos: list[str]):
        super().__init__(f"Assentos inexistentes: {', '.join(assentos)}")
        self.assentos = assentos


# --- Sistema de assentos do cinema ---


def buscar_mapa(sessao_id: int) -> list[dict]:
    resposta = http.get(f"{CINEMA_URL}/sessoes/{sessao_id}/assentos")
    resposta.raise_for_status()
    return resposta.json()["assentos"]


def reservar_assentos(sessao_id: int, assentos: list[str]) -> str:
    resposta = http.post(f"{CINEMA_URL}/sessoes/{sessao_id}/reservas", json={"assentos": assentos})
    if resposta.status_code == 409:
        raise AssentosIndisponiveis(resposta.json()["detail"]["indisponiveis"])
    if resposta.status_code == 422:
        raise AssentosInexistentes(resposta.json()["detail"]["assentos"])
    resposta.raise_for_status()
    return resposta.json()["reserva_id"]


def confirmar_reserva(reserva_id: str) -> None:
    http.post(f"{CINEMA_URL}/reservas/{reserva_id}/confirmar").raise_for_status()


def cancelar_reserva(reserva_id: str) -> None:
    http.delete(f"{CINEMA_URL}/reservas/{reserva_id}").raise_for_status()


# --- Gateway de pagamento ---


# A cobrança tem timeout: sem ele, um gateway travado prenderia o assento para sempre.
TIMEOUT_GATEWAY_S = 10


class PagamentoNaoRealizado(Exception):
    """O gateway falhou e confirmou que nada foi cobrado."""


def cobrar(valor_centavos: int, cartao_token: str, referencia: str) -> dict:
    try:
        resposta = http.post(
            f"{GATEWAY_URL}/cobrancas",
            json={"valor_centavos": valor_centavos, "cartao_token": cartao_token, "referencia": referencia},
            # Se a mesma cobrança for enviada de novo, o gateway não cobra duas vezes
            headers={"Idempotency-Key": referencia},
            timeout=TIMEOUT_GATEWAY_S,
        )
        resposta.raise_for_status()
        return resposta.json()
    except httpx.HTTPError:
        # Erro ou timeout: a cobrança pode ter acontecido ou não.
        # Antes de liberar o assento, pergunta ao gateway.
        cobranca = buscar_cobranca(referencia)
        if cobranca is None:
            raise PagamentoNaoRealizado()
        return cobranca


def buscar_cobranca(referencia: str) -> dict | None:
    resposta = http.get(f"{GATEWAY_URL}/cobrancas", params={"referencia": referencia}, timeout=TIMEOUT_GATEWAY_S)
    resposta.raise_for_status()
    cobrancas = resposta.json()
    return cobrancas[0] if cobrancas else None

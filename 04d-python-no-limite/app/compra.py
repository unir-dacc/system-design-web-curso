"""
Fluxo de compra de ingressos, igual ao da etapa 04: tudo dentro da
requisição. Confere as regras, registra o pedido, segura os assentos no
cinema, cobra no gateway, confirma a venda, emite os ingressos e manda o
e-mail. O cliente espera tudo isso com a requisição aberta.
"""

import re
import uuid
from datetime import datetime
from typing import Any, NoReturn

from app import banco, cache, clientes, notificacoes
from app.config import COTA_MEIA_ENTRADA_PCT, LIMITE_INGRESSOS_POR_CPF, TAXA_CONVENIENCIA_PCT
from app.cpf import cpf_valido, normalizar
from app.erros import ErroHTTP, PagamentoNaoConcluido, PagamentoNaoRealizado

# Pedidos nesses status contam para o limite por CPF e para a cota de meia
STATUS_QUE_CONTAM = ["reservando", "aguardando_pagamento", "confirmado"]

EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+$")


class Pedido:
    def __init__(self, sessao_id: int, nome: str, cpf: str, email: str, subtotal: int, taxa: int,
                 qtd_ingressos: int, qtd_meia: int) -> None:
        self.id = 0
        self.sessao_id = sessao_id
        self.nome = nome
        self.cpf = cpf
        self.email = email
        self.status = "reservando"
        self.subtotal_centavos = subtotal
        self.taxa_centavos = taxa
        self.total_centavos = subtotal + taxa
        self.qtd_ingressos = qtd_ingressos
        self.qtd_meia = qtd_meia
        self.reserva_id = ""
        self.criado_em: datetime | None = None


def validar(dados: Any) -> str:
    """Confere o pedido (as mesmas regras das outras etapas) e devolve o CPF normalizado."""
    if len(dados.nome) < 2:
        raise ErroHTTP(422, "O nome precisa ter pelo menos 2 caracteres")
    if not EMAIL_VALIDO.match(dados.email):
        raise ErroHTTP(422, "E-mail inválido")
    if not dados.cartao_token:
        raise ErroHTTP(422, "cartao_token é obrigatório")
    if not dados.itens:
        raise ErroHTTP(422, "O pedido precisa ter pelo menos um ingresso")
    cpf = normalizar(dados.cpf)
    if not cpf_valido(cpf):
        raise ErroHTTP(422, "CPF inválido")
    for item in dados.itens:
        if not 2 <= len(item.assento) <= 4:
            raise ErroHTTP(422, f"Assento inválido: {item.assento}")
        if item.tipo not in ("inteira", "meia"):
            raise ErroHTTP(422, "O tipo do ingresso deve ser inteira ou meia")
    return cpf


async def realizar_compra(dados: Any) -> Pedido:
    cpf = validar(dados)
    sessao = await banco.buscar_sessao(dados.sessao_id)
    if sessao is None:
        raise ErroHTTP(404, "Sessão não encontrada")

    assentos = [item.assento.upper() for item in dados.itens]
    if len(set(assentos)) != len(assentos):
        raise ErroHTTP(422, "O pedido tem assentos repetidos")
    precos = [sessao.preco_meia_centavos if item.tipo == "meia" else sessao.preco_inteira_centavos for item in dados.itens]
    subtotal = sum(precos)
    taxa = subtotal * TAXA_CONVENIENCIA_PCT // 100
    qtd_meia = sum(1 for item in dados.itens if item.tipo == "meia")

    # 1. Confere as regras e registra o pedido, tudo de uma vez
    pedido = Pedido(sessao.id, dados.nome, cpf, dados.email, subtotal, taxa, len(assentos), qtd_meia)
    await registrar_pedido(pedido, sessao.capacidade)

    # 2. Segura os assentos no sistema do cinema
    try:
        pedido.reserva_id = await clientes.reservar_assentos(sessao.id, assentos)
    except Exception:
        await mudar_status(pedido, "cancelado")  # deixa de contar para o limite
        raise
    pedido.status = "aguardando_pagamento"
    await banco.pool.execute(
        "UPDATE pedidos SET status = $1, reserva_id = $2 WHERE id = $3", pedido.status, pedido.reserva_id, pedido.id
    )
    await cache.mapa_mudou(sessao.id)

    # 3. Cobra no gateway de pagamento (lento). O cliente espera com a
    # requisição aberta; no async, a espera não prende uma thread.
    try:
        cobranca = await clientes.cobrar(pedido.total_centavos, dados.cartao_token, f"pedido-{pedido.id}")
    except PagamentoNaoRealizado:
        # Nada foi cobrado: libera o assento e o pedido deixa de contar para o limite
        await pagamento_nao_deu_certo(pedido, "pagamento_falhou", 503,
                                      "Não foi possível falar com o gateway de pagamento. Nada foi cobrado, tente de novo.")
    await banco.pool.execute("UPDATE pedidos SET cobranca_id = $1 WHERE id = $2", cobranca["id"], pedido.id)
    if cobranca["status"] != "aprovada":
        await pagamento_nao_deu_certo(pedido, "pagamento_recusado", 402, "Pagamento recusado")

    # 4. Confirma a venda no cinema
    await clientes.confirmar_reserva(pedido.reserva_id)
    await cache.mapa_mudou(sessao.id)

    # 5. Emite os ingressos
    ingressos = [(uuid.uuid4().hex, assento, item.tipo, preco) for assento, item, preco in zip(assentos, dados.itens, precos)]
    async with banco.pool.acquire() as conexao, conexao.transaction():
        await conexao.executemany(
            "INSERT INTO ingressos (pedido_id, sessao_id, assento, tipo, preco_centavos, codigo) VALUES ($1, $2, $3, $4, $5, $6)",
            [(pedido.id, sessao.id, assento, tipo, preco, codigo) for codigo, assento, tipo, preco in ingressos],
        )
        await conexao.execute("UPDATE pedidos SET status = 'confirmado' WHERE id = $1", pedido.id)
    pedido.status = "confirmado"

    # 6. Envia o e-mail com os QR codes, ainda dentro da requisição
    await notificacoes.enviar_confirmacao(pedido, sessao, ingressos)
    return pedido


async def registrar_pedido(pedido: Pedido, capacidade: int) -> None:
    """
    Confere o limite por CPF e a cota de meia e registra o pedido, numa única
    transação curta. A trava do banco (pg_advisory_xact_lock) faz os pedidos
    da mesma sessão passarem por aqui um de cada vez.
    """
    async with banco.pool.acquire() as conexao, conexao.transaction():
        await conexao.execute("SELECT pg_advisory_xact_lock($1)", pedido.sessao_id)
        ja_tem: int = await conexao.fetchval(
            "SELECT coalesce(sum(qtd_ingressos), 0) FROM pedidos WHERE sessao_id = $1 AND cpf = $2 AND status = ANY($3)",
            pedido.sessao_id, pedido.cpf, STATUS_QUE_CONTAM,
        )
        if ja_tem + pedido.qtd_ingressos > LIMITE_INGRESSOS_POR_CPF:
            raise ErroHTTP(422, f"Limite de {LIMITE_INGRESSOS_POR_CPF} ingressos por CPF nesta sessão (você já tem {ja_tem})")

        if pedido.qtd_meia:
            cota = capacidade * COTA_MEIA_ENTRADA_PCT // 100
            meias: int = await conexao.fetchval(
                "SELECT coalesce(sum(qtd_meia), 0) FROM pedidos WHERE sessao_id = $1 AND status = ANY($2)",
                pedido.sessao_id, STATUS_QUE_CONTAM,
            )
            if meias + pedido.qtd_meia > cota:
                raise ErroHTTP(422, f"Cota de meia-entrada esgotada ({meias} de {cota} vendidas)")

        linha = await conexao.fetchrow(
            """INSERT INTO pedidos (sessao_id, nome, cpf, email, status, subtotal_centavos, taxa_centavos,
                                    total_centavos, qtd_ingressos, qtd_meia)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id, criado_em""",
            pedido.sessao_id, pedido.nome, pedido.cpf, pedido.email, pedido.status, pedido.subtotal_centavos,
            pedido.taxa_centavos, pedido.total_centavos, pedido.qtd_ingressos, pedido.qtd_meia,
        )
        pedido.id = linha[0]
        pedido.criado_em = linha[1]
    # o fim da transação solta a trava


async def mudar_status(pedido: Pedido, status: str) -> None:
    pedido.status = status
    await banco.pool.execute("UPDATE pedidos SET status = $1 WHERE id = $2", status, pedido.id)


async def pagamento_nao_deu_certo(pedido: Pedido, status: str, codigo: int, detalhe: str) -> NoReturn:
    await clientes.cancelar_reserva(pedido.reserva_id)
    await cache.mapa_mudou(pedido.sessao_id)
    await mudar_status(pedido, status)
    raise PagamentoNaoConcluido(pedido, codigo, detalhe)

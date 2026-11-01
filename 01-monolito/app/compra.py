"""
Fluxo de compra de ingressos.

Esta é a versão INGÊNUA: funciona com poucos usuários, mas cada problema
marcado com ⚠️ vira assunto de uma aula do curso.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clients, notificacoes
from app.config import COTA_MEIA_ENTRADA_PCT, LIMITE_INGRESSOS_POR_CPF, TAXA_CONVENIENCIA_PCT
from app.models import Ingresso, Pedido, Sessao
from app.schemas import CriarPedido


class SessaoNaoEncontrada(Exception):
    pass


class RegraDeNegocio(Exception):
    pass


class PagamentoRecusado(Exception):
    def __init__(self, pedido: Pedido):
        super().__init__("Pagamento recusado")
        self.pedido = pedido


def realizar_compra(db: Session, dados: CriarPedido) -> Pedido:
    sessao = db.get(Sessao, dados.sessao_id)
    if sessao is None:
        raise SessaoNaoEncontrada()

    assentos = [item.assento.upper() for item in dados.itens]
    if len(set(assentos)) != len(assentos):
        raise RegraDeNegocio("O pedido tem assentos repetidos")

    # ⚠️ PROPOSITAL (aula 03): "verifica e depois age" (check-then-act).
    # As duas regras abaixo leem o banco agora, mas os ingressos só são
    # gravados no final, segundos depois. Requisições simultâneas passam
    # todas pela verificação antes de qualquer uma gravar.
    validar_limite_por_cpf(db, sessao, dados.cpf, len(assentos))
    validar_cota_meia_entrada(db, sessao, sum(1 for item in dados.itens if item.tipo == "meia"))

    precos = [sessao.preco_meia_centavos if item.tipo == "meia" else sessao.preco_inteira_centavos for item in dados.itens]
    subtotal = sum(precos)
    taxa = subtotal * TAXA_CONVENIENCIA_PCT // 100

    # 1. Segura os assentos no sistema do cinema (lento)
    reserva_id = clients.reservar_assentos(sessao.id, assentos)

    pedido = Pedido(
        sessao_id=sessao.id,
        nome=dados.nome,
        cpf=dados.cpf,
        email=dados.email,
        status="aguardando_pagamento",
        subtotal_centavos=subtotal,
        taxa_centavos=taxa,
        total_centavos=subtotal + taxa,
        reserva_id=reserva_id,
    )
    db.add(pedido)
    db.commit()

    # 2. Cobra no gateway de pagamento (lento)
    # ⚠️ PROPOSITAL (aula 05): o cliente fica esperando o pagamento com a requisição aberta.
    # ⚠️ PROPOSITAL (aula 07): se o gateway falhar aqui, a reserva fica presa até expirar.
    cobranca = clients.cobrar(pedido.total_centavos, dados.cartao_token, referencia=f"pedido-{pedido.id}")
    pedido.cobranca_id = cobranca["id"]

    if cobranca["status"] != "aprovada":
        clients.cancelar_reserva(reserva_id)
        pedido.status = "pagamento_recusado"
        db.commit()
        raise PagamentoRecusado(pedido)

    # 3. Confirma a venda no cinema (lento)
    clients.confirmar_reserva(reserva_id)

    # 4. Emite os ingressos
    for item, preco in zip(dados.itens, precos):
        pedido.ingressos.append(
            Ingresso(
                sessao_id=sessao.id,
                assento=item.assento.upper(),
                tipo=item.tipo,
                preco_centavos=preco,
                codigo=uuid.uuid4().hex,
            )
        )
    pedido.status = "confirmado"
    db.commit()

    # 5. Envia o e-mail com os QR codes
    # ⚠️ PROPOSITAL (aula 05): gerar imagens e falar com o SMTP dentro da requisição.
    notificacoes.enviar_confirmacao(pedido, sessao)

    return pedido


def validar_limite_por_cpf(db: Session, sessao: Sessao, cpf: str, quantidade: int) -> None:
    ja_comprados = db.scalar(
        select(func.count(Ingresso.id)).join(Pedido).where(Pedido.cpf == cpf, Ingresso.sessao_id == sessao.id)
    )
    if ja_comprados + quantidade > LIMITE_INGRESSOS_POR_CPF:
        raise RegraDeNegocio(
            f"Limite de {LIMITE_INGRESSOS_POR_CPF} ingressos por CPF nesta sessão (você já tem {ja_comprados})"
        )


def validar_cota_meia_entrada(db: Session, sessao: Sessao, quantidade: int) -> None:
    if quantidade == 0:
        return
    cota = sessao.sala.capacidade * COTA_MEIA_ENTRADA_PCT // 100
    vendidas = db.scalar(select(func.count(Ingresso.id)).where(Ingresso.sessao_id == sessao.id, Ingresso.tipo == "meia"))
    if vendidas + quantidade > cota:
        raise RegraDeNegocio(f"Cota de meia-entrada esgotada ({vendidas} de {cota} vendidas)")

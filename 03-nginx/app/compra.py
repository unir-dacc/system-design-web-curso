"""
Fluxo de compra de ingressos.

Esta é a versão INGÊNUA: funciona com poucos usuários, mas cada problema
marcado com ⚠️ vira assunto de uma aula do curso.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cache, clients, notificacoes
from app.config import COTA_MEIA_ENTRADA_PCT, LIMITE_INGRESSOS_POR_CPF, TAXA_CONVENIENCIA_PCT
from app.models import Ingresso, Pedido, Sessao
from app.schemas import CriarPedido

# Pedidos nesses status contam para o limite por CPF e para a cota de meia
STATUS_QUE_CONTAM = ("reservando", "aguardando_pagamento", "confirmado")


class SessaoNaoEncontrada(Exception):
    pass


class RegraDeNegocio(Exception):
    pass


class PagamentoRecusado(Exception):
    def __init__(self, pedido: Pedido):
        super().__init__("Pagamento recusado")
        self.pedido = pedido


class FalhaNoPagamento(Exception):
    def __init__(self, pedido: Pedido):
        super().__init__("Falha no gateway de pagamento")
        self.pedido = pedido


def realizar_compra(db: Session, dados: CriarPedido) -> Pedido:
    sessao = db.get(Sessao, dados.sessao_id)
    if sessao is None:
        raise SessaoNaoEncontrada()

    assentos = [item.assento.upper() for item in dados.itens]
    if len(set(assentos)) != len(assentos):
        raise RegraDeNegocio("O pedido tem assentos repetidos")

    precos = [sessao.preco_meia_centavos if item.tipo == "meia" else sessao.preco_inteira_centavos for item in dados.itens]
    subtotal = sum(precos)
    taxa = subtotal * TAXA_CONVENIENCIA_PCT // 100
    qtd_meia = sum(1 for item in dados.itens if item.tipo == "meia")

    # 1. Confere as regras e registra o pedido, tudo de uma vez
    pedido = registrar_pedido(db, sessao, dados, len(assentos), qtd_meia, subtotal, taxa)

    # 2. Segura os assentos no sistema do cinema
    try:
        pedido.reserva_id = clients.reservar_assentos(sessao.id, assentos)
    except Exception:
        pedido.status = "cancelado"  # deixa de contar para o limite
        db.commit()
        raise
    pedido.status = "aguardando_pagamento"
    mapa_mudou(sessao.id)
    db.commit()

    # 3. Cobra no gateway de pagamento (lento)
    # ⚠️ PROPOSITAL: o cliente fica esperando o pagamento com a requisição aberta.
    try:
        cobranca = clients.cobrar(pedido.total_centavos, dados.cartao_token, referencia=f"pedido-{pedido.id}")
    except clients.PagamentoNaoRealizado:
        # Nada foi cobrado: libera o assento e o pedido deixa de contar para o limite
        clients.cancelar_reserva(pedido.reserva_id)
        mapa_mudou(sessao.id)
        pedido.status = "pagamento_falhou"
        db.commit()
        raise FalhaNoPagamento(pedido)
    pedido.cobranca_id = cobranca["id"]

    if cobranca["status"] != "aprovada":
        clients.cancelar_reserva(pedido.reserva_id)
        mapa_mudou(sessao.id)
        pedido.status = "pagamento_recusado"
        db.commit()
        raise PagamentoRecusado(pedido)

    # 4. Confirma a venda no cinema
    clients.confirmar_reserva(pedido.reserva_id)
    mapa_mudou(sessao.id)

    # 5. Emite os ingressos
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

    # 6. Envia o e-mail com os QR codes
    # ⚠️ PROPOSITAL: gerar imagens e falar com o SMTP dentro da requisição.
    notificacoes.enviar_confirmacao(pedido, sessao)

    return pedido



def mapa_mudou(sessao_id: int) -> None:
    """Os assentos da sessão mudaram: a cópia do mapa no cache ficou velha."""
    cache.esquecer(cache.chave_do_mapa(sessao_id))


def registrar_pedido(
    db: Session, sessao: Sessao, dados: CriarPedido, quantidade: int, qtd_meia: int, subtotal: int, taxa: int
) -> Pedido:
    """
    Confere o limite por CPF e a cota de meia e registra o pedido, numa única
    transação curta.

    A trava do banco (pg_advisory_xact_lock) faz os pedidos da mesma sessão
    passarem por aqui um de cada vez, então duas compras simultâneas nunca
    leem o mesmo total. Ela dura só esta transação (milissegundos) e é solta
    no commit, antes das chamadas lentas ao cinema e ao gateway. Como o pedido
    já fica registrado, quem vier depois já conta com ele.
    """
    db.execute(select(func.pg_advisory_xact_lock(sessao.id)))

    ja_tem = db.scalar(
        select(func.coalesce(func.sum(Pedido.qtd_ingressos), 0)).where(
            Pedido.sessao_id == sessao.id, Pedido.cpf == dados.cpf, Pedido.status.in_(STATUS_QUE_CONTAM)
        )
    )
    if ja_tem + quantidade > LIMITE_INGRESSOS_POR_CPF:
        db.rollback()
        raise RegraDeNegocio(f"Limite de {LIMITE_INGRESSOS_POR_CPF} ingressos por CPF nesta sessão (você já tem {ja_tem})")

    if qtd_meia:
        cota = sessao.sala.capacidade * COTA_MEIA_ENTRADA_PCT // 100
        meias = db.scalar(
            select(func.coalesce(func.sum(Pedido.qtd_meia), 0)).where(
                Pedido.sessao_id == sessao.id, Pedido.status.in_(STATUS_QUE_CONTAM)
            )
        )
        if meias + qtd_meia > cota:
            db.rollback()
            raise RegraDeNegocio(f"Cota de meia-entrada esgotada ({meias} de {cota} vendidas)")

    pedido = Pedido(
        sessao_id=sessao.id,
        nome=dados.nome,
        cpf=dados.cpf,
        email=dados.email,
        status="reservando",
        subtotal_centavos=subtotal,
        taxa_centavos=taxa,
        total_centavos=subtotal + taxa,
        qtd_ingressos=quantidade,
        qtd_meia=qtd_meia,
    )
    db.add(pedido)
    db.commit()  # solta a trava
    return pedido

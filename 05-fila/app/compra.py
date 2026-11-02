"""
Fluxo de compra de ingressos.

A compra é dividida em duas partes:

1. Durante a requisição (rápido): confere as regras, registra o pedido,
   segura os assentos no cinema e põe uma tarefa na fila (app/fila.py).
   O cliente recebe "pedido recebido" na hora e não precisa esperar.
2. No worker (app/worker.py): cobra no gateway, confirma a venda no cinema,
   emite os ingressos e avisa o cliente por e-mail, dando certo ou não.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cache, clients, fila, notificacoes
from app.config import COTA_MEIA_ENTRADA_PCT, LIMITE_INGRESSOS_POR_CPF, TAXA_CONVENIENCIA_PCT
from app.db import SessionLocal
from app.models import Ingresso, Pedido, Sessao
from app.schemas import CriarPedido

# Pedidos nesses status contam para o limite por CPF e para a cota de meia
STATUS_QUE_CONTAM = ("reservando", "aguardando_pagamento", "confirmado")


class SessaoNaoEncontrada(Exception):
    pass


class RegraDeNegocio(Exception):
    pass


def realizar_compra(db: Session, dados: CriarPedido) -> Pedido:
    """A parte da compra que acontece durante a requisição: rápida."""
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

    # 3. Põe o resto na fila. O cliente recebe "pedido recebido" na hora e vai
    # embora; o worker conclui a compra e avisa por e-mail, dando certo ou não.
    itens = [[item.assento.upper(), item.tipo, preco] for item, preco in zip(dados.itens, precos)]
    try:
        fila.enfileirar({"pedido_id": pedido.id, "cartao_token": dados.cartao_token, "itens": itens})
    except Exception:
        # Sem fila não há quem conclua a compra: libera os assentos
        clients.cancelar_reserva(pedido.reserva_id)
        mapa_mudou(sessao.id)
        pedido.status = "cancelado"
        db.commit()
        raise
    return pedido


def concluir_compra(pedido_id: int, cartao_token: str, itens: list[list]) -> None:
    """A parte da compra que o worker faz, longe da requisição do usuário."""
    with SessionLocal() as db:
        pedido = db.get(Pedido, pedido_id)
        if pedido is None or pedido.status != "aguardando_pagamento":
            return  # a tarefa voltou para a fila, mas esta compra já tinha sido concluída
        sessao = db.get(Sessao, pedido.sessao_id)
        # Devolve a conexão do banco antes de esperar o gateway
        db.commit()

        # 4. Cobra no gateway de pagamento (lento). Se a tarefa for feita de novo,
        # a mesma referência faz o gateway devolver a cobrança que já existe.
        try:
            cobranca = clients.cobrar(pedido.total_centavos, cartao_token, referencia=f"pedido-{pedido.id}")
        except clients.PagamentoNaoRealizado:
            # Nada foi cobrado: libera o assento e o pedido deixa de contar para o limite
            clients.cancelar_reserva(pedido.reserva_id)
            mapa_mudou(sessao.id)
            pedido.status = "pagamento_falhou"
            db.commit()
            notificacoes.enviar_falha(pedido, sessao, "não conseguimos falar com o sistema de pagamento")
            return
        pedido.cobranca_id = cobranca["id"]

        if cobranca["status"] != "aprovada":
            clients.cancelar_reserva(pedido.reserva_id)
            mapa_mudou(sessao.id)
            pedido.status = "pagamento_recusado"
            db.commit()
            notificacoes.enviar_falha(pedido, sessao, "o pagamento foi recusado")
            return

        # 5. Confirma a venda no cinema
        clients.confirmar_reserva(pedido.reserva_id)
        mapa_mudou(sessao.id)

        # 6. Emite os ingressos
        for assento, tipo, preco in itens:
            pedido.ingressos.append(
                Ingresso(sessao_id=sessao.id, assento=assento, tipo=tipo, preco_centavos=preco, codigo=uuid.uuid4().hex)
            )
        pedido.status = "confirmado"
        db.commit()

        # 7. Envia o e-mail com os QR codes. É por ele que o cliente fica sabendo:
        # ninguém está esperando na tela.
        notificacoes.enviar_confirmacao(pedido, sessao)


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

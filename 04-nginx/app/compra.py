"""
Fluxo de compra de ingressos.

A compra é dividida em duas partes:

1. Durante a requisição (rápido): confere as regras, registra o pedido e
   segura os assentos no sistema do cinema. O cliente recebe o pedido na hora,
   com o status "aguardando_pagamento".
2. Em segundo plano: cobra no gateway, confirma a venda no cinema, emite os
   ingressos e envia o e-mail. O cliente acompanha em GET /pedidos/{id}.
"""

import asyncio
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, notificacoes
from app.config import COTA_MEIA_ENTRADA_PCT, LIMITE_INGRESSOS_POR_CPF, TAXA_CONVENIENCIA_PCT
from app.db import SessionLocal
from app.models import Ingresso, Pedido, Sessao
from app.schemas import CriarPedido

log = logging.getLogger("uvicorn.error")

# Pedidos nesses status contam para o limite por CPF e para a cota de meia
STATUS_QUE_CONTAM = ("reservando", "aguardando_pagamento", "confirmado")

# Guarda as tarefas em andamento: sem uma referência, o Python pode descartá-las
_pagamentos_em_andamento: set[asyncio.Task] = set()


class SessaoNaoEncontrada(Exception):
    pass


class RegraDeNegocio(Exception):
    pass


async def realizar_compra(db: AsyncSession, dados: CriarPedido) -> Pedido:
    sessao = await db.get(Sessao, dados.sessao_id)
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
    pedido = await registrar_pedido(db, sessao, dados, len(assentos), qtd_meia, subtotal, taxa)

    # 2. Segura os assentos no sistema do cinema (lento)
    try:
        pedido.reserva_id = await clients.reservar_assentos(sessao.id, assentos)
    except Exception:
        pedido.status = "cancelado"  # deixa de contar para o limite
        await db.commit()
        raise
    pedido.status = "aguardando_pagamento"
    await db.commit()

    # 3. O resto continua em segundo plano; o cliente recebe o pedido agora.
    # ⚠️ PROPOSITAL: a tarefa vive na memória deste processo. Se ele cair, os
    # pagamentos em andamento se perdem e os pedidos ficam "aguardando_pagamento".
    itens = [(item.assento.upper(), item.tipo, preco) for item, preco in zip(dados.itens, precos)]
    tarefa = asyncio.create_task(concluir_compra(pedido.id, dados.cartao_token, itens))
    _pagamentos_em_andamento.add(tarefa)
    tarefa.add_done_callback(_pagamentos_em_andamento.discard)
    return pedido


async def concluir_compra(pedido_id: int, cartao_token: str, itens: list[tuple[str, str, int]]) -> None:
    try:
        async with SessionLocal() as db:
            pedido = await db.get(Pedido, pedido_id)
            sessao = await db.get(Sessao, pedido.sessao_id)

            # Cobra no gateway de pagamento (lento)
            # ⚠️ PROPOSITAL: se o gateway falhar aqui, a reserva fica presa até expirar.
            cobranca = await clients.cobrar(pedido.total_centavos, cartao_token, referencia=f"pedido-{pedido.id}")
            pedido.cobranca_id = cobranca["id"]

            if cobranca["status"] != "aprovada":
                await clients.cancelar_reserva(pedido.reserva_id)
                pedido.status = "pagamento_recusado"
                await db.commit()
                return

            # Confirma a venda no cinema (lento)
            await clients.confirmar_reserva(pedido.reserva_id)

            # Emite os ingressos
            for assento, tipo, preco in itens:
                pedido.ingressos.append(
                    Ingresso(
                        sessao_id=sessao.id, assento=assento, tipo=tipo, preco_centavos=preco, codigo=uuid.uuid4().hex
                    )
                )
            pedido.status = "confirmado"
            await db.commit()

            # Gerar QR code (CPU) e usar o SMTP (biblioteca síncrona) TRAVARIAM o
            # event loop: esse trabalho roda numa thread separada.
            await asyncio.to_thread(notificacoes.enviar_confirmacao, pedido, sessao)
    except Exception:
        log.exception("Falha ao concluir a compra do pedido %s", pedido_id)


async def registrar_pedido(
    db: AsyncSession, sessao: Sessao, dados: CriarPedido, quantidade: int, qtd_meia: int, subtotal: int, taxa: int
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
    await db.execute(select(func.pg_advisory_xact_lock(sessao.id)))

    ja_tem = await db.scalar(
        select(func.coalesce(func.sum(Pedido.qtd_ingressos), 0)).where(
            Pedido.sessao_id == sessao.id, Pedido.cpf == dados.cpf, Pedido.status.in_(STATUS_QUE_CONTAM)
        )
    )
    if ja_tem + quantidade > LIMITE_INGRESSOS_POR_CPF:
        await db.rollback()
        raise RegraDeNegocio(f"Limite de {LIMITE_INGRESSOS_POR_CPF} ingressos por CPF nesta sessão (você já tem {ja_tem})")

    if qtd_meia:
        cota = sessao.sala.capacidade * COTA_MEIA_ENTRADA_PCT // 100
        meias = await db.scalar(
            select(func.coalesce(func.sum(Pedido.qtd_meia), 0)).where(
                Pedido.sessao_id == sessao.id, Pedido.status.in_(STATUS_QUE_CONTAM)
            )
        )
        if meias + qtd_meia > cota:
            await db.rollback()
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
        ingressos=[],
    )
    db.add(pedido)
    await db.commit()  # solta a trava
    return pedido

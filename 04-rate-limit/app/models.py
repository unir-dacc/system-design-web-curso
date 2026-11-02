from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Filme(Base):
    __tablename__ = "filmes"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str]
    duracao_min: Mapped[int]
    classificacao: Mapped[str] = mapped_column(String(2))
    sinopse: Mapped[str]


class Cinema(Base):
    __tablename__ = "cinemas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str]


class Sala(Base):
    __tablename__ = "salas"

    id: Mapped[int] = mapped_column(primary_key=True)
    cinema_id: Mapped[int] = mapped_column(ForeignKey("cinemas.id"))
    nome: Mapped[str]
    capacidade: Mapped[int]

    cinema: Mapped[Cinema] = relationship()


class Sessao(Base):
    __tablename__ = "sessoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    filme_id: Mapped[int] = mapped_column(ForeignKey("filmes.id"))
    sala_id: Mapped[int] = mapped_column(ForeignKey("salas.id"))
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    preco_inteira_centavos: Mapped[int]

    filme: Mapped[Filme] = relationship()
    sala: Mapped[Sala] = relationship()

    @property
    def preco_meia_centavos(self) -> int:
        return self.preco_inteira_centavos // 2


class Pedido(Base):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    sessao_id: Mapped[int] = mapped_column(ForeignKey("sessoes.id"))
    nome: Mapped[str]
    cpf: Mapped[str] = mapped_column(String(11))
    email: Mapped[str]
    # reservando -> aguardando_pagamento -> confirmado | pagamento_recusado | pagamento_falhou | cancelado
    status: Mapped[str]
    subtotal_centavos: Mapped[int]
    taxa_centavos: Mapped[int]
    total_centavos: Mapped[int]
    # Quantos ingressos e quantas meias o pedido tem: pedidos em andamento
    # também contam para o limite por CPF e para a cota de meia
    qtd_ingressos: Mapped[int]
    qtd_meia: Mapped[int]
    reserva_id: Mapped[str | None]
    cobranca_id: Mapped[str | None]
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    ingressos: Mapped[list["Ingresso"]] = relationship(back_populates="pedido")


class Ingresso(Base):
    __tablename__ = "ingressos"

    # ⚠️ PROPOSITAL: o Postgres NÃO cria índice para chave estrangeira.
    # Sem índice em sessao_id e pedido_id, contar ingressos de uma sessão
    # vira uma varredura da tabela inteira conforme as vendas crescem.
    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"))
    sessao_id: Mapped[int] = mapped_column(ForeignKey("sessoes.id"))
    assento: Mapped[str] = mapped_column(String(4))
    tipo: Mapped[str] = mapped_column(String(7))  # inteira | meia
    preco_centavos: Mapped[int]
    codigo: Mapped[str] = mapped_column(String(32), unique=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    pedido: Mapped[Pedido] = relationship(back_populates="ingressos")

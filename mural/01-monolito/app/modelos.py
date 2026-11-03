"""
As tabelas do Mural, do jeito que o ORM (SQLAlchemy) cria.

⚠️ PROPOSITAL: os únicos índices são os das chaves primárias, que o banco cria
sozinho. Uma ForeignKey NÃO cria índice no Postgres: procurar os posts de um
autor ou os comentários de um post é ler a tabela inteira.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Seguidor(Base):
    """Quem segue quem. A chave primária é o par (quem segue, quem é seguido)."""

    __tablename__ = "seguidores"

    seguidor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    seguido_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    texto: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Carregado só quando alguém usa post.autor: uma consulta a mais, na hora
    autor: Mapped[Usuario] = relationship()


class Curtida(Base):
    """Cada um curte um post uma vez só: a chave primária é o par (post, usuário)."""

    __tablename__ = "curtidas"

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Comentario(Base):
    __tablename__ = "comentarios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    texto: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    autor: Mapped[Usuario] = relationship()

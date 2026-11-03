"""
As tabelas do Mural, do jeito que o ORM (SQLAlchemy) cria.

Uma ForeignKey NÃO cria índice no Postgres: além dos das chaves primárias, que
o banco cria sozinho, os índices são declarados aqui, um para cada busca que o
Mural faz (os posts de um autor, os comentários de um post).
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
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
    # O feed e o perfil procuram os posts de um autor, dos mais novos para os
    # mais antigos. Um índice composto: primeiro o autor, e dentro de cada autor,
    # os posts já em ordem de data. A ordem das colunas importa.
    __table_args__ = (Index("posts_autor_id_criado_em_idx", "autor_id", "criado_em"),)

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
    # Os comentários de um post, dos mais novos para os mais antigos
    __table_args__ = (Index("comentarios_post_id_criado_em_idx", "post_id", "criado_em"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    texto: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    autor: Mapped[Usuario] = relationship()

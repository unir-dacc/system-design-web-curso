from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import TAMANHO_MAXIMO_DO_TEXTO
from app.modelos import Curtida, Post


class AutorOut(BaseModel):
    id: int
    nome: str


class PostOut(BaseModel):
    id: int
    autor: AutorOut
    texto: str
    criado_em: datetime
    curtidas: int


class Escrever(BaseModel):
    # Sem login, para simplificar: quem escreve diz quem é
    usuario_id: int
    texto: str = Field(min_length=1, max_length=TAMANHO_MAXIMO_DO_TEXTO)


class Curtir(BaseModel):
    usuario_id: int


def post_da_linha(linha, autor: dict | None = None) -> dict:
    """Uma linha do SQL (id, texto, criado_em, curtidas, e autor_id/autor_nome) no formato da resposta."""
    return {
        "id": linha.id,
        "autor": autor or {"id": linha.autor_id, "nome": linha.autor_nome},
        "texto": linha.texto,
        "criado_em": linha.criado_em,
        "curtidas": linha.curtidas,
    }


def posts_out(db: Session, posts: list[Post]) -> list[PostOut]:
    """Pelo ORM, nas escritas: os posts com as curtidas, numa consulta agrupada por post."""
    ids = [post.id for post in posts]
    # ⚠️ PROPOSITAL: o total ainda é contado na hora, curtida por curtida
    curtidas = dict(db.execute(select(Curtida.post_id, func.count()).where(Curtida.post_id.in_(ids)).group_by(Curtida.post_id)).all()) if ids else {}
    return [
        PostOut(
            id=post.id,
            autor=AutorOut(id=post.autor.id, nome=post.autor.nome),
            texto=post.texto,
            criado_em=post.criado_em,
            curtidas=curtidas.get(post.id, 0),
        )
        for post in posts
    ]

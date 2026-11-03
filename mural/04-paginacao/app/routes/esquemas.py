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


def posts_out(db: Session, posts: list[Post]) -> list[PostOut]:
    """Monta uma página de posts com UMA consulta a mais, para as curtidas de todos.

    O autor já vem junto com o post (joinedload, nas rotas), e as curtidas da
    página inteira saem de uma consulta só, agrupada por post. Uma página com
    20 posts são 2 consultas, e não dezenas.
    """
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

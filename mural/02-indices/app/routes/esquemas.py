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


def post_out(db: Session, post: Post) -> PostOut:
    # ⚠️ PROPOSITAL: o jeito mais direto com o ORM. Para cada post, "post.autor"
    # faz uma consulta (se o autor ainda não foi carregado) e o total de curtidas
    # faz outra. Uma página com 20 posts vira dezenas de consultas.
    return PostOut(
        id=post.id,
        autor=AutorOut(id=post.autor.id, nome=post.autor.nome),
        texto=post.texto,
        criado_em=post.criado_em,
        curtidas=db.scalar(select(func.count()).select_from(Curtida).where(Curtida.post_id == post.id)),
    )

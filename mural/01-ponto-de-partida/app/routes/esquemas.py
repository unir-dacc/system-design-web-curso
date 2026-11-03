from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import TAMANHO_MAXIMO_DO_TEXTO
from app.modelos import Curtida, Post, Usuario


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


async def post_out(db: AsyncSession, post: Post) -> PostOut:
    # ⚠️ PROPOSITAL: o jeito mais direto com o ORM. Para cada post, uma consulta
    # para o autor (se ele ainda não foi carregado nesta requisição) e outra
    # para o total de curtidas. Uma página com 20 posts vira dezenas de consultas.
    autor = await db.get(Usuario, post.autor_id)
    curtidas = await db.scalar(select(func.count()).select_from(Curtida).where(Curtida.post_id == post.id))
    return PostOut(id=post.id, autor=AutorOut(id=autor.id, nome=autor.nome), texto=post.texto, criado_em=post.criado_em, curtidas=curtidas)

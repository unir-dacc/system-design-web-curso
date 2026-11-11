from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import COMENTARIOS_POR_PAGINA
from app.db import get_db
from app.modelos import Comentario, Curtida, Post, Usuario
from app.routes.esquemas import AutorOut, Curtir, Escrever, PostOut, post_out

router = APIRouter(prefix="/posts", tags=["posts"])


class ComentarioOut(BaseModel):
    id: int
    autor: AutorOut
    texto: str
    criado_em: datetime


class PostComComentariosOut(PostOut):
    comentarios: list[ComentarioOut]


class CurtidasOut(BaseModel):
    post_id: int
    curtidas: int


def comentario_out(comentario: Comentario, autor: Usuario) -> ComentarioOut:
    return ComentarioOut(id=comentario.id, autor=AutorOut(id=autor.id, nome=autor.nome), texto=comentario.texto, criado_em=comentario.criado_em)


async def buscar_autor(db: AsyncSession, usuario_id: int) -> Usuario:
    autor = await db.get(Usuario, usuario_id)
    if autor is None:
        raise HTTPException(404, "Usuário não encontrado")
    return autor


@router.post("", status_code=201, response_model=PostOut)
async def publicar(dados: Escrever, db: AsyncSession = Depends(get_db)):
    autor = await buscar_autor(db, dados.usuario_id)
    post = Post(autor_id=autor.id, texto=dados.texto)
    db.add(post)
    await db.commit()
    return post_out(post, autor)


@router.get("/{post_id}", response_model=PostComComentariosOut)
async def ver_post(post_id: int, db: AsyncSession = Depends(get_db)):
    """O post, com os comentários mais recentes. Duas consultas, com os autores juntos (JOIN)."""
    linha = (await db.execute(select(Post, Usuario).join(Usuario, Usuario.id == Post.autor_id).where(Post.id == post_id))).first()
    if linha is None:
        raise HTTPException(404, "Post não encontrado")
    post, autor = linha
    # O índice (post_id, criado_em) leva direto aos comentários mais novos do post
    comentarios = (await db.execute(
        select(Comentario, Usuario)
        .join(Usuario, Usuario.id == Comentario.autor_id)
        .where(Comentario.post_id == post_id)
        .order_by(Comentario.criado_em.desc())
        .limit(COMENTARIOS_POR_PAGINA)
    )).all()
    return PostComComentariosOut(**post_out(post, autor).model_dump(), comentarios=[comentario_out(c, a) for c, a in comentarios])


@router.post("/{post_id}/curtidas", response_model=CurtidasOut)
async def curtir(post_id: int, dados: Curtir, response: Response, db: AsyncSession = Depends(get_db)):
    """Curte o post (201) e devolve o total de curtidas. Curtir de novo não conta duas vezes (200)."""
    try:
        # Se essa pessoa já tinha curtido, a chave primária (post, usuário) barra
        # a repetida, e o ON CONFLICT faz o banco simplesmente não gravar. Sem
        # consultar antes: mesmo com duas curtidas iguais ao mesmo tempo, só uma entra.
        nova = (await db.execute(
            insert(Curtida).values(post_id=post_id, usuario_id=dados.usuario_id).on_conflict_do_nothing().returning(Curtida.post_id)
        )).first()
    except IntegrityError:
        # As ForeignKeys barraram: o post ou o usuário não existe
        await db.rollback()
        raise HTTPException(404, "Post ou usuário não encontrado")
    if nova:
        # Soma 1 no total do post, na mesma transação da curtida: as duas coisas
        # são gravadas juntas, ou nenhuma. O próprio banco soma (curtidas + 1),
        # então duas curtidas ao mesmo tempo não se atropelam.
        total = await db.scalar(update(Post).where(Post.id == post_id).values(curtidas=Post.curtidas + 1).returning(Post.curtidas))
        response.status_code = 201
    else:
        total = await db.scalar(select(Post.curtidas).where(Post.id == post_id))
        response.status_code = 200
    await db.commit()
    return CurtidasOut(post_id=post_id, curtidas=total)


@router.post("/{post_id}/comentarios", status_code=201, response_model=ComentarioOut)
async def comentar(post_id: int, dados: Escrever, db: AsyncSession = Depends(get_db)):
    autor = await buscar_autor(db, dados.usuario_id)
    comentario = Comentario(post_id=post_id, autor_id=autor.id, texto=dados.texto)
    db.add(comentario)
    try:
        await db.commit()
    except IntegrityError:
        # A ForeignKey barrou: o post não existe
        await db.rollback()
        raise HTTPException(404, "Post não encontrado")
    return comentario_out(comentario, autor)

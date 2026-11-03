from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
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


async def buscar_post(db: AsyncSession, post_id: int) -> Post:
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(404, "Post não encontrado")
    return post


async def conferir_usuario(db: AsyncSession, usuario_id: int) -> None:
    if await db.get(Usuario, usuario_id) is None:
        raise HTTPException(404, "Usuário não encontrado")


async def comentario_out(db: AsyncSession, comentario: Comentario) -> ComentarioOut:
    autor = await db.get(Usuario, comentario.autor_id)  # uma consulta por comentário, se o autor ainda não foi carregado
    return ComentarioOut(id=comentario.id, autor=AutorOut(id=autor.id, nome=autor.nome), texto=comentario.texto, criado_em=comentario.criado_em)


@router.post("", status_code=201, response_model=PostOut)
async def publicar(dados: Escrever, db: AsyncSession = Depends(get_db)):
    await conferir_usuario(db, dados.usuario_id)
    post = Post(autor_id=dados.usuario_id, texto=dados.texto)
    db.add(post)
    await db.commit()
    return await post_out(db, post)


@router.get("/{post_id}", response_model=PostComComentariosOut)
async def ver_post(post_id: int, db: AsyncSession = Depends(get_db)):
    """O post, com os comentários mais recentes."""
    post = await buscar_post(db, post_id)
    # O índice (post_id, criado_em) leva direto aos comentários mais novos do post
    comentarios = (await db.scalars(
        select(Comentario).where(Comentario.post_id == post_id).order_by(Comentario.criado_em.desc()).limit(COMENTARIOS_POR_PAGINA)
    )).all()
    return PostComComentariosOut(**(await post_out(db, post)).model_dump(), comentarios=[await comentario_out(db, c) for c in comentarios])


@router.post("/{post_id}/curtidas", response_model=CurtidasOut)
async def curtir(post_id: int, dados: Curtir, response: Response, db: AsyncSession = Depends(get_db)):
    """Curte o post (201) e devolve o total de curtidas. Curtir de novo não conta duas vezes (200)."""
    await buscar_post(db, post_id)
    await conferir_usuario(db, dados.usuario_id)
    response.status_code = 200
    if await db.get(Curtida, (post_id, dados.usuario_id)) is None:
        db.add(Curtida(post_id=post_id, usuario_id=dados.usuario_id))
        try:
            await db.commit()
            response.status_code = 201
        except IntegrityError:
            await db.rollback()  # o mesmo usuário curtiu duas vezes ao mesmo tempo: a chave primária barrou a segunda
    # ⚠️ PROPOSITAL: o total é contado na hora, curtida por curtida
    total = await db.scalar(select(func.count()).select_from(Curtida).where(Curtida.post_id == post_id))
    return CurtidasOut(post_id=post_id, curtidas=total)


@router.post("/{post_id}/comentarios", status_code=201, response_model=ComentarioOut)
async def comentar(post_id: int, dados: Escrever, db: AsyncSession = Depends(get_db)):
    await buscar_post(db, post_id)
    await conferir_usuario(db, dados.usuario_id)
    comentario = Comentario(post_id=post_id, autor_id=dados.usuario_id, texto=dados.texto)
    db.add(comentario)
    await db.commit()
    return await comentario_out(db, comentario)

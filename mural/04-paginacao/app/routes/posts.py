from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import COMENTARIOS_POR_PAGINA
from app.db import get_db
from app.modelos import Comentario, Curtida, Post, Usuario
from app.routes.esquemas import AutorOut, Curtir, Escrever, PostOut, posts_out

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


def buscar_post(db: Session, post_id: int) -> Post:
    post = db.get(Post, post_id, options=[joinedload(Post.autor)])
    if post is None:
        raise HTTPException(404, "Post não encontrado")
    return post


def conferir_usuario(db: Session, usuario_id: int) -> None:
    if db.get(Usuario, usuario_id) is None:
        raise HTTPException(404, "Usuário não encontrado")


def comentario_out(comentario: Comentario) -> ComentarioOut:
    autor = comentario.autor
    return ComentarioOut(id=comentario.id, autor=AutorOut(id=autor.id, nome=autor.nome), texto=comentario.texto, criado_em=comentario.criado_em)


@router.post("", status_code=201, response_model=PostOut)
def publicar(dados: Escrever, db: Session = Depends(get_db)):
    conferir_usuario(db, dados.usuario_id)
    post = Post(autor_id=dados.usuario_id, texto=dados.texto)
    db.add(post)
    db.commit()
    return posts_out(db, [post])[0]


@router.get("/{post_id}", response_model=PostComComentariosOut)
def ver_post(post_id: int, db: Session = Depends(get_db)):
    """O post, com os comentários mais recentes."""
    post = buscar_post(db, post_id)
    # O índice (post_id, criado_em) leva direto aos comentários mais novos do post
    # Os autores dos comentários vêm na mesma consulta (JOIN)
    comentarios = db.scalars(
        select(Comentario)
        .options(joinedload(Comentario.autor))
        .where(Comentario.post_id == post_id)
        .order_by(Comentario.criado_em.desc())
        .limit(COMENTARIOS_POR_PAGINA)
    ).all()
    return PostComComentariosOut(**posts_out(db, [post])[0].model_dump(), comentarios=[comentario_out(c) for c in comentarios])


@router.post("/{post_id}/curtidas", response_model=CurtidasOut)
def curtir(post_id: int, dados: Curtir, response: Response, db: Session = Depends(get_db)):
    """Curte o post (201) e devolve o total de curtidas. Curtir de novo não conta duas vezes (200)."""
    buscar_post(db, post_id)
    conferir_usuario(db, dados.usuario_id)
    response.status_code = 200
    if db.get(Curtida, (post_id, dados.usuario_id)) is None:
        db.add(Curtida(post_id=post_id, usuario_id=dados.usuario_id))
        try:
            db.commit()
            response.status_code = 201
        except IntegrityError:
            db.rollback()  # o mesmo usuário curtiu duas vezes ao mesmo tempo: a chave primária barrou a segunda
    # ⚠️ PROPOSITAL: o total é contado na hora, curtida por curtida
    total = db.scalar(select(func.count()).select_from(Curtida).where(Curtida.post_id == post_id))
    return CurtidasOut(post_id=post_id, curtidas=total)


@router.post("/{post_id}/comentarios", status_code=201, response_model=ComentarioOut)
def comentar(post_id: int, dados: Escrever, db: Session = Depends(get_db)):
    buscar_post(db, post_id)
    conferir_usuario(db, dados.usuario_id)
    comentario = Comentario(post_id=post_id, autor_id=dados.usuario_id, texto=dados.texto)
    db.add(comentario)
    db.commit()
    return comentario_out(comentario)

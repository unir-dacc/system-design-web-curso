from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.config import COMENTARIOS_POR_PAGINA
from app.db import get_db
from app.modelos import Comentario, Curtida, Post, Usuario
from app.routes.esquemas import AutorOut, Curtir, Escrever, PostOut, post_da_linha, posts_out

router = APIRouter(prefix="/posts", tags=["posts"])

# A página do post é leitura: SQL escrito uma vez só, sem ORM (veja feed.py).
# As escritas, abaixo, continuam pelo ORM.

# ⚠️ PROPOSITAL: as curtidas ainda são contadas na hora, curtida por curtida
POST = text("""
    SELECT posts.id, posts.texto, posts.criado_em,
           usuarios.id AS autor_id, usuarios.nome AS autor_nome,
           (SELECT count(*) FROM curtidas WHERE curtidas.post_id = posts.id) AS curtidas
    FROM posts
    JOIN usuarios ON usuarios.id = posts.autor_id
    WHERE posts.id = :post_id
""")

# O índice (post_id, criado_em) leva direto aos comentários mais novos do post
COMENTARIOS = text("""
    SELECT comentarios.id, comentarios.texto, comentarios.criado_em,
           usuarios.id AS autor_id, usuarios.nome AS autor_nome
    FROM comentarios
    JOIN usuarios ON usuarios.id = comentarios.autor_id
    WHERE comentarios.post_id = :post_id
    ORDER BY comentarios.criado_em DESC
    LIMIT :por_pagina
""")


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
    post = db.execute(POST, {"post_id": post_id}).first()
    if post is None:
        raise HTTPException(404, "Post não encontrado")
    comentarios = db.execute(COMENTARIOS, {"post_id": post_id, "por_pagina": COMENTARIOS_POR_PAGINA})
    return {
        **post_da_linha(post),
        "comentarios": [
            {"id": c.id, "autor": {"id": c.autor_id, "nome": c.autor_nome}, "texto": c.texto, "criado_em": c.criado_em}
            for c in comentarios
        ],
    }


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

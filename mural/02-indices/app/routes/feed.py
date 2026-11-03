from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import POSTS_POR_PAGINA
from app.db import get_db
from app.modelos import Post, Seguidor, Usuario
from app.routes.esquemas import PostOut, post_out

# As rotas são "async": enquanto uma espera o banco, o processo atende as outras
router = APIRouter(tags=["feed"])


class PerfilOut(BaseModel):
    id: int
    nome: str
    posts: list[PostOut]


@router.get("/feed", response_model=list[PostOut])
async def feed(usuario_id: int, pagina: int = Query(1, ge=1), db: AsyncSession = Depends(get_db)):
    """Os posts de quem o usuário segue, dos mais novos para os mais antigos."""
    quem_eu_sigo = select(Seguidor.seguido_id).where(Seguidor.seguidor_id == usuario_id)
    # O índice (autor_id, criado_em) leva direto aos posts de cada pessoa que eu
    # sigo, já em ordem de data.
    # ⚠️ PROPOSITAL: a paginação pula as páginas anteriores com OFFSET: a página
    # 50 lê e descarta os 980 posts que vêm antes.
    posts = (await db.scalars(
        select(Post)
        .where(Post.autor_id.in_(quem_eu_sigo))
        .order_by(Post.criado_em.desc())
        .offset((pagina - 1) * POSTS_POR_PAGINA)
        .limit(POSTS_POR_PAGINA)
    )).all()
    return [await post_out(db, post) for post in posts]


@router.get("/usuarios/{usuario_id}", response_model=PerfilOut)
async def perfil(usuario_id: int, pagina: int = Query(1, ge=1), db: AsyncSession = Depends(get_db)):
    """O perfil: o usuário e os posts dele, dos mais novos para os mais antigos."""
    usuario = await db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuário não encontrado")
    posts = (await db.scalars(
        select(Post)
        .where(Post.autor_id == usuario_id)
        .order_by(Post.criado_em.desc())
        .offset((pagina - 1) * POSTS_POR_PAGINA)
        .limit(POSTS_POR_PAGINA)
    )).all()
    return PerfilOut(id=usuario.id, nome=usuario.nome, posts=[await post_out(db, post) for post in posts])

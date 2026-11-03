from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import POSTS_POR_PAGINA
from app.db import get_db
from app.modelos import Post, Seguidor, Usuario
from app.routes.esquemas import PostOut, posts_out

# As rotas são "def" (síncronas): o FastAPI roda cada uma numa thread de um
# pool com 40 threads. Com 40 requisições lentas ao mesmo tempo, a 41ª espera.
router = APIRouter(tags=["feed"])


class PerfilOut(BaseModel):
    id: int
    nome: str
    posts: list[PostOut]


@router.get("/feed", response_model=list[PostOut])
def feed(usuario_id: int, pagina: int = Query(1, ge=1), db: Session = Depends(get_db)):
    """Os posts de quem o usuário segue, dos mais novos para os mais antigos."""
    quem_eu_sigo = select(Seguidor.seguido_id).where(Seguidor.seguidor_id == usuario_id)
    # O índice (autor_id, criado_em) leva direto aos posts de cada pessoa que eu
    # sigo, já em ordem de data.
    # ⚠️ PROPOSITAL: a paginação pula as páginas anteriores com OFFSET: a página
    # 50 lê e descarta os 980 posts que vêm antes.
    posts = db.scalars(
        select(Post)
        .options(joinedload(Post.autor))  # o autor vem na mesma consulta (JOIN)
        .where(Post.autor_id.in_(quem_eu_sigo))
        .order_by(Post.criado_em.desc())
        .offset((pagina - 1) * POSTS_POR_PAGINA)
        .limit(POSTS_POR_PAGINA)
    ).all()
    return posts_out(db, posts)


@router.get("/usuarios/{usuario_id}", response_model=PerfilOut)
def perfil(usuario_id: int, pagina: int = Query(1, ge=1), db: Session = Depends(get_db)):
    """O perfil: o usuário e os posts dele, dos mais novos para os mais antigos."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuário não encontrado")
    # Todos os posts são do mesmo autor, que já foi carregado acima: o ORM
    # reaproveita o usuário que já tem na sessão, sem consultar de novo
    posts = db.scalars(
        select(Post)
        .where(Post.autor_id == usuario_id)
        .order_by(Post.criado_em.desc())
        .offset((pagina - 1) * POSTS_POR_PAGINA)
        .limit(POSTS_POR_PAGINA)
    ).all()
    return PerfilOut(id=usuario.id, nome=usuario.nome, posts=posts_out(db, posts))

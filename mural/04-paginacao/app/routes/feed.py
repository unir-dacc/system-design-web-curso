from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, true
from sqlalchemy.orm import Session, aliased, joinedload

from app.config import POSTS_POR_PAGINA
from app.db import get_db
from app.modelos import Post, Seguidor, Usuario
from app.routes.esquemas import PostOut, posts_out

# As rotas são "def" (síncronas): o FastAPI roda cada uma numa thread de um
# pool com 40 threads. Com 40 requisições lentas ao mesmo tempo, a 41ª espera.
router = APIRouter(tags=["feed"])

# A paginação é por cursor: a próxima página pede os posts mais antigos que o
# último que eu vi (antes_de = o criado_em dele). Nenhuma página precisa ler e
# descartar as anteriores, como fazia o OFFSET.
# (Dois posts criados no mesmo microssegundo poderiam ficar de fora na virada
# da página; um sistema de verdade desempata pelo id.)


class PerfilOut(BaseModel):
    id: int
    nome: str
    posts: list[PostOut]


@router.get("/feed", response_model=list[PostOut])
def feed(usuario_id: int, antes_de: datetime | None = None, db: Session = Depends(get_db)):
    """Os posts de quem o usuário segue, dos mais novos para os mais antigos.

    A próxima página: antes_de = o criado_em do último post desta.
    """
    # Para cada pessoa que eu sigo, só os 20 posts mais recentes (LATERAL: uma
    # subconsulta por pessoa seguida). O índice (autor_id, criado_em) entrega
    # esses 20 já em ordem, sem ler o resto dos posts dela. Depois, dos 20 de
    # cada um, ficam os 20 mais novos de todos.
    dela = select(Post).where(Post.autor_id == Seguidor.seguido_id)
    if antes_de is not None:
        dela = dela.where(Post.criado_em < antes_de)
    recentes = dela.order_by(Post.criado_em.desc()).limit(POSTS_POR_PAGINA).lateral("recentes")
    post = aliased(Post, recentes)
    posts = db.scalars(
        select(post)
        .options(joinedload(post.autor))  # o autor vem na mesma consulta (JOIN)
        .select_from(Seguidor)
        .join(recentes, true())
        .where(Seguidor.seguidor_id == usuario_id)
        .order_by(post.criado_em.desc())
        .limit(POSTS_POR_PAGINA)
    ).all()
    return posts_out(db, posts)


@router.get("/usuarios/{usuario_id}", response_model=PerfilOut)
def perfil(usuario_id: int, antes_de: datetime | None = None, db: Session = Depends(get_db)):
    """O perfil: o usuário e os posts dele, dos mais novos para os mais antigos."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuário não encontrado")
    # Todos os posts são do mesmo autor, que já foi carregado acima: o ORM
    # reaproveita o usuário que já tem na sessão, sem consultar de novo
    consulta = select(Post).where(Post.autor_id == usuario_id)
    if antes_de is not None:
        consulta = consulta.where(Post.criado_em < antes_de)
    posts = db.scalars(consulta.order_by(Post.criado_em.desc()).limit(POSTS_POR_PAGINA)).all()
    return PerfilOut(id=usuario.id, nome=usuario.nome, posts=posts_out(db, posts))

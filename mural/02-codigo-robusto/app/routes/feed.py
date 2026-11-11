from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import POSTS_POR_PAGINA
from app.db import get_db
from app.modelos import Post, Seguidor, Usuario
from app.routes.esquemas import PostOut, post_out

# As rotas são "async": enquanto uma espera o banco, o processo atende as outras
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
async def feed(usuario_id: int, antes_de: datetime | None = None, db: AsyncSession = Depends(get_db)):
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
    # O autor de cada post vem na mesma consulta (JOIN): a página inteira sai de
    # uma ida ao banco só
    pagina = (await db.execute(
        select(post, Usuario)
        .select_from(Seguidor)
        .join(recentes, true())
        .join(Usuario, Usuario.id == post.autor_id)
        .where(Seguidor.seguidor_id == usuario_id)
        .order_by(post.criado_em.desc())
        .limit(POSTS_POR_PAGINA)
    )).all()
    return [post_out(p, autor) for p, autor in pagina]


@router.get("/usuarios/{usuario_id}", response_model=PerfilOut)
async def perfil(usuario_id: int, antes_de: datetime | None = None, db: AsyncSession = Depends(get_db)):
    """O perfil: o usuário e os posts dele, dos mais novos para os mais antigos."""
    usuario = await db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuário não encontrado")
    consulta = select(Post).where(Post.autor_id == usuario_id)
    if antes_de is not None:
        consulta = consulta.where(Post.criado_em < antes_de)
    posts = (await db.scalars(consulta.order_by(Post.criado_em.desc()).limit(POSTS_POR_PAGINA))).all()
    # Todos os posts são do mesmo autor, que já foi lido acima
    return PerfilOut(id=usuario.id, nome=usuario.nome, posts=[post_out(p, usuario) for p in posts])

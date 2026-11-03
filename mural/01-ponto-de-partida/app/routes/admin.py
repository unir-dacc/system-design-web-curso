import random

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import POSTS_INICIAIS, USUARIOS_INICIAIS
from app.db import get_db

# Rotas de apoio às aulas: o teste de carga usa antes de começar. Não
# existiriam em produção.
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reset")
async def reset(db: AsyncSession = Depends(get_db)):
    """Volta ao começo da aula: apaga o que foi criado depois da carga inicial."""
    # Pode demorar mais que o limite das rotas normais
    await db.execute(text("SET LOCAL statement_timeout = 0"))
    marco = {"marco": await db.scalar(text("SELECT preparada_em FROM aula"))}
    await db.execute(text("DELETE FROM curtidas WHERE criado_em > :marco"), marco)
    await db.execute(text("DELETE FROM comentarios WHERE criado_em > :marco"), marco)
    await db.execute(text("DELETE FROM posts WHERE criado_em > :marco"), marco)
    await db.commit()
    return {"status": "posts, curtidas e comentários da aula apagados"}


@router.get("/amostra")
async def amostra(quantidade: int = 1000, db: AsyncSession = Depends(get_db)):
    """Usuários e posts que existem, sorteados, e a celebridade com mais seguidores."""
    await db.execute(text("SET LOCAL statement_timeout = 0"))
    celebridade = await db.scalar(text("SELECT seguido_id FROM seguidores GROUP BY seguido_id ORDER BY count(*) DESC LIMIT 1"))
    return {
        "usuarios": random.sample(range(1, USUARIOS_INICIAIS + 1), min(quantidade, USUARIOS_INICIAIS)),
        "posts": random.sample(range(1, POSTS_INICIAIS + 1), min(quantidade, POSTS_INICIAIS)),
        "total_de_usuarios": USUARIOS_INICIAIS,
        "celebridade": celebridade,
    }

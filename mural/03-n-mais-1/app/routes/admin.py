import random

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import POSTS_INICIAIS, USUARIOS_INICIAIS
from app.db import get_db

# Rotas de apoio às aulas: o teste de carga usa antes de começar. Não
# existiriam em produção.
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reset")
def reset(db: Session = Depends(get_db)):
    """Volta ao começo da aula: apaga o que foi criado depois da carga inicial."""
    marco = {"marco": db.scalar(text("SELECT preparada_em FROM aula"))}
    db.execute(text("DELETE FROM curtidas WHERE criado_em > :marco"), marco)
    db.execute(text("DELETE FROM comentarios WHERE criado_em > :marco"), marco)
    db.execute(text("DELETE FROM posts WHERE criado_em > :marco"), marco)
    db.commit()
    return {"status": "posts, curtidas e comentários da aula apagados"}


@router.get("/amostra")
def amostra(quantidade: int = 1000, db: Session = Depends(get_db)):
    """Usuários e posts que existem, sorteados, e a celebridade com mais seguidores."""
    celebridade = db.scalar(text("SELECT seguido_id FROM seguidores GROUP BY seguido_id ORDER BY count(*) DESC LIMIT 1"))
    return {
        "usuarios": random.sample(range(1, USUARIOS_INICIAIS + 1), min(quantidade, USUARIOS_INICIAIS)),
        "posts": random.sample(range(1, POSTS_INICIAIS + 1), min(quantidade, POSTS_INICIAIS)),
        "total_de_usuarios": USUARIOS_INICIAIS,
        "celebridade": celebridade,
    }

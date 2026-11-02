import random

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import LINKS_INICIAIS
from app.db import get_db

# Rotas de apoio às aulas: o teste de carga usa antes de começar. Não
# existiriam em produção.
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reset")
def reset(db: Session = Depends(get_db)):
    """Volta ao começo da aula: apaga os links criados e zera os cliques."""
    db.execute(text("DELETE FROM links WHERE id > :ultimo"), {"ultimo": LINKS_INICIAIS})
    db.execute(text("UPDATE links SET cliques = 0 WHERE cliques > 0"))
    db.execute(text("SELECT setval('links_id_seq', :ultimo)"), {"ultimo": LINKS_INICIAIS})
    db.commit()
    return {"status": "links criados apagados e cliques zerados"}


@router.get("/amostra")
def amostra(quantidade: int = 1000, db: Session = Depends(get_db)):
    """Códigos de links que existem, sorteados (busca pelo id, que tem índice)."""
    ids = random.sample(range(1, LINKS_INICIAIS + 1), min(quantidade, LINKS_INICIAIS))
    codigos = db.scalars(text("SELECT codigo FROM links WHERE id = ANY(:ids)"), {"ids": ids}).all()
    random.shuffle(codigos)
    return {"codigos": codigos}


@router.get("/cliques")
def total_de_cliques(db: Session = Depends(get_db)):
    """Quantos cliques o encurtador contou, somando todos os links."""
    return {"total": db.scalar(text("SELECT coalesce(sum(cliques), 0) FROM links"))}

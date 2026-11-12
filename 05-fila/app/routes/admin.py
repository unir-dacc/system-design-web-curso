from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import cache, fila
from app.db import get_db

# Rota de apoio às aulas: os testes de carga chamam antes de começar, para que
# toda rodada parta do mesmo estado. Não existiria em produção.
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reset")
def reset(db: Session = Depends(get_db)):
    db.execute(text("TRUNCATE ingressos, pedidos RESTART IDENTITY"))
    # Zera as estatísticas de cada consulta (pg_stat_statements): depois do
    # teste, o pgHero mostra só a rodada
    db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_stat_statements"))
    db.execute(text("SELECT pg_stat_statements_reset()"))
    db.commit()
    cache.limpar()
    return {"status": "pedidos, ingressos, cache e fila apagados"}


@router.get("/fila")
def tamanho_da_fila():
    """Quantas compras estão esperando o worker (o teste de carga acompanha durante a rodada)."""
    return {"compras_na_fila": fila.tamanho()}

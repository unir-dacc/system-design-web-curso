from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.db import get_db

# Rota de apoio às aulas: os testes de carga chamam antes de começar, para que
# toda rodada parta do mesmo estado. Não existiria em produção.
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reset")
async def reset(db: AsyncSession = Depends(get_db)):
    await db.execute(text("TRUNCATE ingressos, pedidos RESTART IDENTITY"))
    # Zera as estatísticas de cada consulta (pg_stat_statements): depois do
    # teste, o pgHero mostra só a rodada
    await db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_stat_statements"))
    await db.execute(text("SELECT pg_stat_statements_reset()"))
    await db.commit()
    await cache.limpar()
    return {"status": "pedidos, ingressos e cache apagados"}

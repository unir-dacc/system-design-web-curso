from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

# Rota de apoio às aulas: os testes de carga chamam antes de começar, para que
# toda rodada parta do mesmo estado. Não existiria em produção.
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reset")
async def reset(db: AsyncSession = Depends(get_db)):
    await db.execute(text("TRUNCATE ingressos, pedidos RESTART IDENTITY"))
    await db.commit()
    return {"status": "pedidos e ingressos apagados"}

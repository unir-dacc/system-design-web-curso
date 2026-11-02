import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SEED_PATH
from app.models import Cinema, Filme, Sala, Sessao


async def carregar_catalogo(db: AsyncSession) -> None:
    """Popula filmes, cinemas, salas e sessões a partir do mesmo arquivo usado pelo sistema do cinema."""
    if await db.scalar(select(func.count()).select_from(Filme)):
        return

    with open(SEED_PATH) as f:
        catalogo = json.load(f)

    db.add_all(Filme(**f) for f in catalogo["filmes"])
    db.add_all(Cinema(**c) for c in catalogo["cinemas"])
    db.add_all(
        Sala(
            id=s["id"],
            cinema_id=s["cinema_id"],
            nome=s["nome"],
            capacidade=len(s["fileiras"]) * s["assentos_por_fileira"],
        )
        for s in catalogo["salas"]
    )
    db.add_all(Sessao(**{**s, "inicio": datetime.fromisoformat(s["inicio"])}) for s in catalogo["sessoes"])
    await db.commit()

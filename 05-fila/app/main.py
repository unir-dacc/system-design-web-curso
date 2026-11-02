import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401 (registra as tabelas no Base)
from app.db import Base, SessionLocal, engine
from app import fila
from app.routes import admin, catalogo, ingressos, pedidos
from app.routes import fila as rotas_da_fila
from app.seed import carregar_catalogo


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conexao:
        await conexao.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        await carregar_catalogo(db)

    # O liberador da fila roda em segundo plano enquanto a aplicação estiver de pé.
    # Com um único processo, só existe um liberador.
    liberador = asyncio.create_task(fila.liberador())
    yield
    liberador.cancel()


app = FastAPI(title="Ingressa", version="05-fila", lifespan=lifespan)
app.include_router(catalogo.router)
app.include_router(pedidos.router)
app.include_router(ingressos.router)
app.include_router(rotas_da_fila.router)
app.include_router(admin.router)


@app.get("/health", tags=["infra"])
async def health():
    return {"status": "ok"}

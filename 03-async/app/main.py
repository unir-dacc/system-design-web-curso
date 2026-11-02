from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401 (registra as tabelas no Base)
from app.db import Base, SessionLocal, engine
from app.routes import admin, catalogo, ingressos, pedidos
from app.seed import carregar_catalogo


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conexao:
        await conexao.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        await carregar_catalogo(db)
    yield


app = FastAPI(title="Ingressa", version="03-async", lifespan=lifespan)
app.include_router(catalogo.router)
app.include_router(pedidos.router)
app.include_router(ingressos.router)
app.include_router(admin.router)


@app.get("/health", tags=["infra"])
async def health():
    return {"status": "ok"}

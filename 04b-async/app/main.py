from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models  # noqa: F401 (registra as tabelas no Base)
from app.db import Base, engine
from app.routes import admin, catalogo, ingressos, pedidos
from app.seed import carregar_catalogo


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Os backends sobem ao mesmo tempo. A trava do banco faz um de cada vez criar
    # as tabelas e o catálogo; os outros encontram tudo pronto.
    async with engine.begin() as conexao:
        await conexao.execute(select(func.pg_advisory_xact_lock(0)))
        await conexao.run_sync(Base.metadata.create_all)
        # A carga do catálogo é a mesma das outras etapas (síncrona), rodando
        # sobre a conexão assíncrona
        await conexao.run_sync(lambda c: carregar_catalogo(Session(bind=c)))
    yield


app = FastAPI(title="Ingressa", version="04b-async", lifespan=lifespan)
app.include_router(catalogo.router)
app.include_router(pedidos.router)
app.include_router(ingressos.router)
app.include_router(admin.router)


@app.get("/health", tags=["infra"])
async def health():
    return {"status": "ok"}

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401 (registra as tabelas no Base)
from app.db import Base, SessionLocal, engine
from app.routes import admin, catalogo, ingressos, pedidos
from app.seed import carregar_catalogo


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        carregar_catalogo(db)
    yield


app = FastAPI(title="Ingressa", version="01-monolito", lifespan=lifespan)
app.include_router(catalogo.router)
app.include_router(pedidos.router)
app.include_router(ingressos.router)
app.include_router(admin.router)


@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}

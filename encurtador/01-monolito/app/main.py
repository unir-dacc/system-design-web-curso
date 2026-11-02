from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import func, select

from app import banco
from app.db import engine
from app.routes import admin, links


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Na primeira subida, criar os links iniciais leva alguns segundos
    with engine.begin() as conexao:
        conexao.execute(select(func.pg_advisory_xact_lock(0)))
        banco.preparar(conexao)
    yield


app = FastAPI(title="Encurtador de URL", version="01-monolito", lifespan=lifespan)


@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}


app.include_router(admin.router)
# Por último: "/{codigo}" pega qualquer caminho que sobrar
app.include_router(links.router)

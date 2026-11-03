from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import func, select

from app import banco
from app.db import engine
from app.routes import admin, feed, posts


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Na primeira subida, criar a rede inicial leva alguns minutos
    with engine.begin() as conexao:
        conexao.execute(select(func.pg_advisory_xact_lock(0)))
        banco.preparar(conexao)
    yield


app = FastAPI(title="Mural", version="01-monolito", lifespan=lifespan)


@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}


app.include_router(feed.router)
app.include_router(posts.router)
app.include_router(admin.router)

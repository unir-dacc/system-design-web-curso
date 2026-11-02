from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SemConexaoLivre

from app import banco
from app.db import engine
from app.routes import admin, links


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Na primeira subida, criar os links iniciais leva cerca de um minuto
    with engine.begin() as conexao:
        conexao.execute(select(func.pg_advisory_xact_lock(0)))
        banco.preparar(conexao)
    yield


app = FastAPI(title="Encurtador de URL", version="02-consertos", lifespan=lifespan)


# Passou do limite de tempo (app/db.py): responde na hora que está sobrecarregado
@app.exception_handler(SemConexaoLivre)
@app.exception_handler(OperationalError)
async def sobrecarregado(request: Request, erro: Exception):
    return JSONResponse({"detail": "Encurtador sobrecarregado, tente de novo em instantes"}, status_code=503)


@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}


app.include_router(admin.router)
# Por último: "/{codigo}" pega qualquer caminho que sobrar
app.include_router(links.router)

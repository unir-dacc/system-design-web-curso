import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app import banco
from app.config import DATABASE_URL_CARGA
from app.db import engine
from app.routes import admin, feed, posts

# O código do Postgres para "consulta cancelada" (o statement_timeout)
CONSULTA_CANCELADA = "57014"


def preparar_o_banco():
    # Todos os processos de todas as réplicas sobem juntos: a trava faz um de
    # cada vez passar por aqui, e só o primeiro cria a rede inicial
    carga = create_engine(DATABASE_URL_CARGA)
    with carga.begin() as conexao:
        conexao.execute(select(func.pg_advisory_xact_lock(0)))
        banco.preparar(conexao)
    carga.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Na primeira subida, criar a rede inicial leva alguns minutos
    await asyncio.to_thread(preparar_o_banco)
    yield
    await engine.dispose()


app = FastAPI(title="Mural", version="01-ponto-de-partida", lifespan=lifespan)


# O banco não deu conta a tempo: responde 503 na hora, em vez de deixar a
# requisição pendurada
@app.exception_handler(PoolTimeoutError)
async def sem_conexao_livre(request: Request, erro: PoolTimeoutError):
    return JSONResponse({"detail": "O banco está ocupado demais (nenhuma conexão livre)"}, status_code=503)


@app.exception_handler(DBAPIError)
async def erro_do_banco(request: Request, erro: DBAPIError):
    if getattr(erro.orig, "pgcode", None) == CONSULTA_CANCELADA:
        return JSONResponse({"detail": "O banco está ocupado demais (a consulta passou do limite)"}, status_code=503)
    return JSONResponse({"detail": "Erro no banco"}, status_code=500)


@app.get("/health", tags=["infra"])
async def health():
    return {"status": "ok"}


app.include_router(feed.router)
app.include_router(posts.router)
app.include_router(admin.router)

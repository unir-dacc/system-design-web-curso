import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, func, select, text
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
    # cada vez passar por aqui, e só o primeiro cria a rede inicial (ou
    # acrescenta o que falta na rede da etapa 01)
    carga = create_engine(DATABASE_URL_CARGA)
    with carga.connect() as conexao:
        # Tenta pegar a trava a cada meio segundo, em vez de ficar parado esperando:
        # quem espera parado segura uma foto antiga do banco, e o VACUUM lá embaixo
        # não pode apagar as linhas que essa foto ainda enxerga
        while not conexao.scalar(select(func.pg_try_advisory_lock(0))):
            conexao.commit()
            time.sleep(0.5)
        conexao.commit()
        with conexao.begin():
            mexeu = banco.preparar(conexao)
        if mexeu:
            # Preencher o total de curtidas reescreveu boa parte dos posts e deixou
            # linhas mortas para trás. Limpa agora, antes de abrir as portas: senão
            # a limpeza automática (o autovacuum) roda no meio da aula. E grava no
            # disco tudo o que foi escrito (CHECKPOINT), pelo mesmo motivo
            sem_transacao = conexao.execution_options(isolation_level="AUTOCOMMIT")
            sem_transacao.execute(text("VACUUM ANALYZE posts"))
            sem_transacao.execute(text("CHECKPOINT"))
        conexao.execute(select(func.pg_advisory_unlock(0)))
        conexao.commit()
    carga.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Na primeira subida, criar a rede inicial leva alguns minutos
    await asyncio.to_thread(preparar_o_banco)
    yield
    await engine.dispose()


app = FastAPI(title="Mural", version="02-codigo-robusto", lifespan=lifespan)


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

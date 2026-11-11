from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import CONEXOES_POR_PROCESSO, DATABASE_URL, ESPERA_POR_CONEXAO_S, LIMITE_DA_CONSULTA_S

engine = create_async_engine(
    DATABASE_URL,
    pool_size=CONEXOES_POR_PROCESSO,
    max_overflow=0,
    # Esperando uma conexão livre do pool: desiste depois do limite (503)
    pool_timeout=ESPERA_POR_CONEXAO_S,
    # Nenhuma consulta passa do limite: o Postgres cancela e libera a conexão (503)
    connect_args={"server_settings": {"statement_timeout": str(LIMITE_DA_CONSULTA_S * 1000)}},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as db:
        yield db

from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import DATABASE_URL

# O mesmo driver (psycopg), agora no modo assíncrono: enquanto uma consulta
# espera o banco, o processo atende outras requisições, sem precisar de uma
# thread para cada uma. Até 40 consultas ao mesmo tempo por processo.
engine = create_async_engine(DATABASE_URL, pool_size=40, max_overflow=0)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


# AsyncAttrs: no async, o ORM não busca uma relação sozinho quando alguém lê
# sessao.filme; quem precisa pede, com "await sessao.awaitable_attrs.filme".
class Base(AsyncAttrs, DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as db:
        yield db

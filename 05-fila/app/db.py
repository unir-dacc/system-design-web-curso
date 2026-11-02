from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import DATABASE_URL

# Não existe mais o limite de 40 threads: agora o limite de quantas requisições
# usam o banco ao mesmo tempo é o tamanho deste pool.
engine = create_async_engine(DATABASE_URL, pool_size=40, max_overflow=0)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as db:
        yield db

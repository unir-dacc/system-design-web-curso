from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

# Uma conexão para cada uma das 40 threads do FastAPI. Com menos conexões que
# threads, as requisições ficam presas esperando conexão e estouram o timeout.
# Cada requisição pode segurar a conexão enquanto espera os sistemas externos.
engine = create_engine(DATABASE_URL, pool_size=40, max_overflow=0)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# "async" de propósito, mesmo com o resto síncrono: assim o FastAPI fecha a
# sessão sem precisar de uma thread livre. Com "def", sob carga extrema todas
# as threads ficam esperando conexão e nenhuma consegue devolver a sua (deadlock).
async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

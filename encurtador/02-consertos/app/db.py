from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_URL, LIMITE_DA_CONSULTA_MS, LIMITE_PARA_PEGAR_CONEXAO_S

# Uma conexão para cada uma das 40 threads do FastAPI.
#
# Limites de tempo: sob sobrecarga, é melhor responder "tente de novo" na hora
# do que deixar as requisições se acumulando até o encurtador travar.
# - pool_timeout: quanto o app espera por uma conexão livre
# - statement_timeout: quanto o Postgres deixa uma consulta rodar antes de desistir
engine = create_engine(
    DATABASE_URL,
    pool_size=40,
    max_overflow=0,
    pool_timeout=LIMITE_PARA_PEGAR_CONEXAO_S,
    connect_args={"options": f"-c statement_timeout={LIMITE_DA_CONSULTA_MS}"},
)
SessionLocal = sessionmaker(engine)


# "async" de propósito, mesmo com o resto síncrono: assim o FastAPI fecha a
# sessão sem precisar de uma thread livre. Com "def", sob carga extrema todas
# as threads ficam esperando conexão e nenhuma consegue devolver a sua (deadlock).
async def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

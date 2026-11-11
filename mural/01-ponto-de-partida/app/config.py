import os

# As rotas usam o driver assíncrono (asyncpg); a carga inicial, o síncrono (psycopg)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://mural:mural@postgres:5432/mural")
DATABASE_URL_CARGA = os.getenv("DATABASE_URL_CARGA", "postgresql+psycopg://mural:mural@postgres:5432/mural")

# Conexões com o banco em cada processo do app. No total, réplicas × processos
# × conexões precisa caber no max_connections do Postgres (100, o padrão).
CONEXOES_POR_PROCESSO = int(os.getenv("CONEXOES_POR_PROCESSO", "5"))

# Quanto tempo uma requisição pode esperar o banco. O público desiste em 5 s:
# o Mural desiste antes (2 s esperando uma conexão livre + 3 s de consulta) e
# responde 503 na hora, em vez de ocupar o banco com quem já foi embora
ESPERA_POR_CONEXAO_S = 2
LIMITE_DA_CONSULTA_S = 3

# O tamanho da rede quando a aula começa (criada na primeira subida)
USUARIOS_INICIAIS = int(os.getenv("USUARIOS_INICIAIS", "100000"))
POSTS_INICIAIS = int(os.getenv("POSTS_INICIAIS", "1000000"))
CURTIDAS_INICIAIS = int(os.getenv("CURTIDAS_INICIAIS", "5000000"))
COMENTARIOS_INICIAIS = int(os.getenv("COMENTARIOS_INICIAIS", "500000"))

POSTS_POR_PAGINA = 20
COMENTARIOS_POR_PAGINA = 20
TAMANHO_MAXIMO_DO_TEXTO = 500

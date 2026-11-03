import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://mural:mural@postgres:5432/mural")

# O tamanho da rede quando a aula começa (criada na primeira subida)
USUARIOS_INICIAIS = int(os.getenv("USUARIOS_INICIAIS", "100000"))
POSTS_INICIAIS = int(os.getenv("POSTS_INICIAIS", "1000000"))
CURTIDAS_INICIAIS = int(os.getenv("CURTIDAS_INICIAIS", "5000000"))
COMENTARIOS_INICIAIS = int(os.getenv("COMENTARIOS_INICIAIS", "500000"))

POSTS_POR_PAGINA = 20
COMENTARIOS_POR_PAGINA = 20
TAMANHO_MAXIMO_DO_TEXTO = 500

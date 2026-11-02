import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://encurtador:encurtador@postgres:5432/encurtador")

# Quantos links o encurtador já tem quando a aula começa (criados na primeira subida)
LINKS_INICIAIS = int(os.getenv("LINKS_INICIAIS", "1000000"))

# O endereço dos links curtos, como o usuário vê
ENDERECO_PUBLICO = os.getenv("ENDERECO_PUBLICO", "http://localhost:8000")

TAMANHO_MAXIMO_DA_URL = 2048

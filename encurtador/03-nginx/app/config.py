import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://encurtador:encurtador@postgres:5432/encurtador")

# Quantos links o encurtador já tem quando a aula começa (criados na primeira subida)
LINKS_INICIAIS = int(os.getenv("LINKS_INICIAIS", "1000000"))

# O endereço dos links curtos, como o usuário vê
ENDERECO_PUBLICO = os.getenv("ENDERECO_PUBLICO", "http://localhost:8000")

TAMANHO_MAXIMO_DA_URL = 2048

# O código curto: o número do link codificado pelo Sqids (app/banco.py), com
# este alfabeto embaralhado (base 62: 0-9, a-z, A-Z) e pelo menos 7 caracteres
ALFABETO_DOS_CODIGOS = "Fs3Kd9QmZr1xVbT7nWc0LpY5gHj2Ek8qPa6NtUoXlRiz4GwDySCfvMeJAhOuIB"
TAMANHO_DO_CODIGO = 7

# Limites de tempo (app/db.py): passou disso, o encurtador responde 503
# ("tente de novo") em vez de deixar a requisição esperando
LIMITE_DA_CONSULTA_MS = int(os.getenv("LIMITE_DA_CONSULTA_MS", "2000"))
LIMITE_PARA_PEGAR_CONEXAO_S = float(os.getenv("LIMITE_PARA_PEGAR_CONEXAO_S", "2"))

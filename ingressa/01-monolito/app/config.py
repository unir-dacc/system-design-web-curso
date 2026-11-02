import os
from datetime import timedelta, timezone

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://ingressa:ingressa@postgres:5432/ingressa")
CINEMA_URL = os.getenv("CINEMA_URL", "http://sistema-cinema:8000")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway-pagamento:8000")
SMTP_HOST = os.getenv("SMTP_HOST", "mailpit")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SEED_PATH = os.getenv("SEED_PATH", "/seed/catalogo.json")

# Horários são exibidos no fuso das sessões do catálogo
FUSO_HORARIO = timezone(timedelta(hours=-4))

# Regras de negócio
TAXA_CONVENIENCIA_PCT = 10
LIMITE_INGRESSOS_POR_CPF = 6  # por sessão
COTA_MEIA_ENTRADA_PCT = 40  # Lei 12.933/2013: 40% dos ingressos da sessão

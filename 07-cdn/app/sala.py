"""
Sala de espera (Redis).

Quando chega mais gente do que o Ingressa aguenta, em vez de recusar o excesso
(429) e perder essas pessoas, cada uma recebe uma senha, como num cartório:

- Ao chegar, o usuário pega a próxima senha (POST /sala).
- O porteiro (uma thread do worker) libera um número fixo de senhas por
  segundo, um pouco abaixo do que o Ingressa aguenta.
- Enquanto espera, o usuário pergunta a vez dele (GET /sala/{senha}). A
  resposta diz em quantos segundos perguntar de novo (Retry-After), para que
  milhares de pessoas esperando custem pouco.
- Quando a senha é liberada, ele recebe um passe. A programação, o mapa e a
  compra só atendem quem tem um passe válido (app/routes/sala.py).

O passe é assinado (HMAC): só o Ingressa sabe gerar um passe válido, então
ninguém fura a fila inventando um.
"""

import hashlib
import hmac
import os

from app.cache import r

SEGREDO = os.getenv("SEGREDO_DA_SALA", "troque-em-producao").encode()

ULTIMA_SENHA = "sala:ultima_senha"  # a senha do último que chegou
LIBERADAS = "sala:liberadas"  # todas as senhas até esta já podem entrar
TAXA = "sala:liberadas_por_segundo"  # o porteiro anota aqui o ritmo dele

# Libera até ARGV[1] senhas, sem passar de quem já chegou. Roda dentro do
# Redis, de uma vez só (atômico).
_liberar = r.register_script(
    """
    local ultima = tonumber(redis.call('GET', KEYS[1]) or 0)
    local liberadas = tonumber(redis.call('GET', KEYS[2]) or 0)
    local novo = math.min(ultima, liberadas + tonumber(ARGV[1]))
    redis.call('SET', KEYS[2], novo)
    return novo
    """
)


def entrar() -> int:
    return r.incr(ULTIMA_SENHA)


def liberadas() -> int:
    return int(r.get(LIBERADAS) or 0)


def liberar(quantidade: int) -> int:
    return _liberar(keys=[ULTIMA_SENHA, LIBERADAS], args=[quantidade])


def anotar_taxa(por_segundo: int) -> None:
    r.set(TAXA, por_segundo)


def taxa() -> int:
    return int(r.get(TAXA) or 1)


def passe(senha: int) -> str:
    assinatura = hmac.new(SEGREDO, str(senha).encode(), hashlib.sha256).hexdigest()[:16]
    return f"{senha}.{assinatura}"


def passe_valido(valor: str | None) -> bool:
    if not valor or "." not in valor:
        return False
    senha = valor.split(".", 1)[0]
    if not senha.isdigit() or not hmac.compare_digest(valor, passe(int(senha))):
        return False
    return int(senha) <= liberadas()

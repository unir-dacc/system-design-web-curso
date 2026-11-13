import math

from fastapi import APIRouter, Header, HTTPException, Response

from app import sala

router = APIRouter(tags=["sala de espera"])


def situacao(senha: int, response: Response) -> dict:
    na_frente = senha - sala.liberadas()
    if na_frente <= 0:
        return {"senha": senha, "liberado": True, "passe": sala.passe(senha)}
    # Volta quando for mais ou menos a sua vez (entre 1 e 60 segundos). Cada
    # pergunta custa CPU dos backends: com milhares de pessoas esperando,
    # perguntar a cada poucos segundos pesaria mais do que a própria venda.
    # Chegar um pouco depois da vez não tem problema: o passe continua valendo.
    espera_s = na_frente / sala.taxa()
    response.headers["Retry-After"] = str(min(60, max(1, math.ceil(espera_s))))
    return {"senha": senha, "liberado": False, "pessoas_na_frente": na_frente, "espera_estimada_s": round(espera_s)}


@router.post("/sala")
def entrar_na_sala(response: Response):
    return situacao(sala.entrar(), response)


@router.get("/sala/{senha}")
def consultar_a_vez(senha: int, response: Response):
    return situacao(senha, response)


def exige_passe(x_passe: str | None = Header(default=None)) -> None:
    """Só atende quem já passou pela sala de espera (cabeçalho X-Passe)."""
    if not sala.passe_valido(x_passe):
        raise HTTPException(403, "Entre na sala de espera (POST /sala) e aguarde a sua vez")

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import ENDERECO_PUBLICO, TAMANHO_MAXIMO_DA_URL
from app.db import get_db

# As rotas são "def" (síncronas): o FastAPI roda cada uma numa thread de um
# pool com 40 threads. Com 40 requisições lentas ao mesmo tempo, a 41ª espera.
router = APIRouter(tags=["links"])


class CriarLink(BaseModel):
    url: str = Field(max_length=TAMANHO_MAXIMO_DA_URL)

    @field_validator("url")
    @classmethod
    def validar_url(cls, valor: str) -> str:
        if not valor.startswith(("http://", "https://")):
            raise ValueError("A URL precisa começar com http:// ou https://")
        return valor


class LinkOut(BaseModel):
    codigo: str
    url: str
    link_curto: str


class EstatisticasOut(BaseModel):
    codigo: str
    url: str
    cliques: int
    criado_em: datetime


@router.post("/links", status_code=201, response_model=LinkOut)
def criar_link(dados: CriarLink, db: Session = Depends(get_db)):
    # O código sai do próximo número da sequência (app/banco.py): único por construção
    codigo = db.scalar(
        text("INSERT INTO links (id, codigo, url) SELECT n, codigo_curto(n), :url FROM nextval('links_id_seq') AS n RETURNING codigo"),
        {"url": dados.url},
    )
    db.commit()
    return LinkOut(codigo=codigo, url=dados.url, link_curto=f"{ENDERECO_PUBLICO}/{codigo}")


@router.get("/links/{codigo}/estatisticas", response_model=EstatisticasOut)
def estatisticas(codigo: str, db: Session = Depends(get_db)):
    link = db.execute(text("SELECT codigo, url, cliques, criado_em FROM links WHERE codigo = :codigo"), {"codigo": codigo}).first()
    if link is None:
        raise HTTPException(404, "Link não encontrado")
    return EstatisticasOut(**link._mapping)


# Fica por último: qualquer outro caminho é um código curto
@router.get("/{codigo}")
def redirecionar(codigo: str, db: Session = Depends(get_db)):
    # Acha o link e conta o clique numa instrução só.
    # ⚠️ PROPOSITAL: cada clique é uma escrita no banco, na linha do link. Quando
    # um link viraliza, todos os cliques disputam a mesma linha.
    url = db.scalar(text("UPDATE links SET cliques = cliques + 1 WHERE codigo = :codigo RETURNING url"), {"codigo": codigo})
    db.commit()
    if url is None:
        raise HTTPException(404, "Link não encontrado")
    return RedirectResponse(url, status_code=302)

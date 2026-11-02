from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Ingresso
from app.notificacoes import gerar_qrcode_png
from app.schemas import IngressoOut

router = APIRouter(tags=["ingressos"])


def buscar_ingresso(db: Session, codigo: str) -> Ingresso:
    ingresso = db.scalar(select(Ingresso).where(Ingresso.codigo == codigo))
    if ingresso is None:
        raise HTTPException(404, "Ingresso não encontrado")
    return ingresso


@router.get("/ingressos/{codigo}", response_model=IngressoOut)
def detalhar_ingresso(codigo: str, db: Session = Depends(get_db)):
    return IngressoOut.model_validate(buscar_ingresso(db, codigo))


@router.get("/ingressos/{codigo}/qrcode")
def qrcode_do_ingresso(codigo: str, db: Session = Depends(get_db)):
    ingresso = buscar_ingresso(db, codigo)
    return Response(gerar_qrcode_png(ingresso.codigo), media_type="image/png")

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Ingresso
from app.notificacoes import gerar_qrcode_png
from app.schemas import IngressoOut

router = APIRouter(tags=["ingressos"])


async def buscar_ingresso(db: AsyncSession, codigo: str) -> Ingresso:
    ingresso = await db.scalar(select(Ingresso).where(Ingresso.codigo == codigo))
    if ingresso is None:
        raise HTTPException(404, "Ingresso não encontrado")
    return ingresso


@router.get("/ingressos/{codigo}", response_model=IngressoOut)
async def detalhar_ingresso(codigo: str, db: AsyncSession = Depends(get_db)):
    return IngressoOut.model_validate(await buscar_ingresso(db, codigo))


@router.get("/ingressos/{codigo}/qrcode")
async def qrcode_do_ingresso(codigo: str, db: AsyncSession = Depends(get_db)):
    ingresso = await buscar_ingresso(db, codigo)
    # Gerar a imagem é trabalho de CPU: numa thread, para não travar as outras requisições
    return Response(await asyncio.to_thread(gerar_qrcode_png, ingresso.codigo), media_type="image/png")

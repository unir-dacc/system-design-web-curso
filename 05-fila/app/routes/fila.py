from fastapi import APIRouter, HTTPException

from app import fila

router = APIRouter(prefix="/fila", tags=["fila virtual"])


@router.post("", status_code=201)
async def entrar_na_fila():
    return await fila.entrar()


@router.get("")
async def estado_da_fila():
    return await fila.estado()


@router.get("/{senha}")
async def consultar_senha(senha: int):
    situacao = await fila.consultar(senha)
    if situacao is None:
        raise HTTPException(404, "Senha não encontrada")
    return situacao

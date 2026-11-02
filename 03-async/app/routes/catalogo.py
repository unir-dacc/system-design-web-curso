from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.config import COTA_MEIA_ENTRADA_PCT, FUSO_HORARIO
from app.db import SessionLocal, get_db
from app.models import Filme, Ingresso, Pedido, Sessao
from app.schemas import FilmeOut, MapaDeAssentosOut, ResumoSessaoOut, SessaoOut

# As rotas são "async def": todas rodam num único event loop. Enquanto uma
# requisição espera (banco, cache, cinema), o loop atende as outras.
router = APIRouter(tags=["catálogo"])


def para_sessao_out(sessao: Sessao) -> SessaoOut:
    return SessaoOut(
        id=sessao.id,
        filme_id=sessao.filme_id,
        filme=sessao.filme.titulo,
        cinema=sessao.sala.cinema.nome,
        sala=sessao.sala.nome,
        inicio=sessao.inicio.astimezone(FUSO_HORARIO),
        preco_inteira_centavos=sessao.preco_inteira_centavos,
        preco_meia_centavos=sessao.preco_meia_centavos,
    )


async def buscar_sessao(db: AsyncSession, sessao_id: int) -> Sessao:
    sessao = await db.get(Sessao, sessao_id)
    if sessao is None:
        raise HTTPException(404, "Sessão não encontrada")
    return sessao


@router.get("/filmes", response_model=list[FilmeOut])
async def listar_filmes(db: AsyncSession = Depends(get_db)):
    filmes = (await db.scalars(select(Filme).order_by(Filme.id))).all()
    return [FilmeOut.model_validate(f) for f in filmes]


@router.get("/sessoes", response_model=list[SessaoOut])
async def listar_sessoes(filme_id: int | None = None, db: AsyncSession = Depends(get_db)):
    consulta = select(Sessao).order_by(Sessao.inicio)
    if filme_id is not None:
        consulta = consulta.where(Sessao.filme_id == filme_id)
    return [para_sessao_out(s) for s in (await db.scalars(consulta)).all()]


@router.get("/sessoes/{sessao_id}", response_model=SessaoOut)
async def detalhar_sessao(sessao_id: int, db: AsyncSession = Depends(get_db)):
    return para_sessao_out(await buscar_sessao(db, sessao_id))


@router.get("/sessoes/{sessao_id}/assentos", response_model=MapaDeAssentosOut)
async def mapa_de_assentos(sessao_id: int):
    # Usa o banco só para conferir a sessão e devolve a conexão logo em seguida,
    # antes de esperar o cache (ou o cinema, se o mapa não estiver guardado).
    async with SessionLocal() as db:
        await buscar_sessao(db, sessao_id)
    assentos = await cache.mapa_de_assentos(sessao_id)
    return MapaDeAssentosOut(
        sessao_id=sessao_id,
        livres=sum(1 for a in assentos if a["status"] == "livre"),
        assentos=assentos,
    )


@router.get("/sessoes/{sessao_id}/resumo", response_model=ResumoSessaoOut)
async def resumo_de_vendas(sessao_id: int, db: AsyncSession = Depends(get_db)):
    sessao = await buscar_sessao(db, sessao_id)
    vendidos = await db.scalar(select(func.count(Ingresso.id)).where(Ingresso.sessao_id == sessao_id))
    meia = await db.scalar(select(func.count(Ingresso.id)).where(Ingresso.sessao_id == sessao_id, Ingresso.tipo == "meia"))
    por_cpf = (
        select(func.count(Ingresso.id).label("quantidade"))
        .join(Pedido)
        .where(Ingresso.sessao_id == sessao_id)
        .group_by(Pedido.cpf)
        .subquery()
    )
    maior_compra = await db.scalar(select(func.coalesce(func.max(por_cpf.c.quantidade), 0)))
    return ResumoSessaoOut(
        sessao_id=sessao_id,
        capacidade=sessao.sala.capacidade,
        ingressos_vendidos=vendidos,
        meia_vendidas=meia,
        cota_meia=sessao.sala.capacidade * COTA_MEIA_ENTRADA_PCT // 100,
        maior_compra_por_cpf=maior_compra,
    )

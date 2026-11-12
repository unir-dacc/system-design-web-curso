from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache, clients
from app.config import COTA_MEIA_ENTRADA_PCT, FUSO_HORARIO, MAPA_TTL_S, PROGRAMACAO_TTL_S
from app.db import get_db
from app.models import Filme, Ingresso, Pedido, Sessao
from app.schemas import FilmeOut, MapaDeAssentosOut, ResumoSessaoOut, SessaoOut

# As rotas são "async def": rodam todas no mesmo processo, sem uma thread para
# cada uma. Enquanto uma espera o banco, o Redis ou o cinema, o processo atende
# as outras. Não há mais o limite de 40 requisições ao mesmo tempo.
router = APIRouter(tags=["catálogo"])

LISTA_DE_FILMES = TypeAdapter(list[FilmeOut])
LISTA_DE_SESSOES = TypeAdapter(list[SessaoOut])


async def para_sessao_out(sessao: Sessao) -> SessaoOut:
    # ⚠️ PROPOSITAL: cada filme, sala e cinema abaixo dispara uma consulta
    # extra no banco (problema N+1).
    filme = await sessao.awaitable_attrs.filme
    sala = await sessao.awaitable_attrs.sala
    cinema = await sala.awaitable_attrs.cinema
    return SessaoOut(
        id=sessao.id,
        filme_id=sessao.filme_id,
        filme=filme.titulo,
        cinema=cinema.nome,
        sala=sala.nome,
        inicio=sessao.inicio.astimezone(FUSO_HORARIO),
        preco_inteira_centavos=sessao.preco_inteira_centavos,
        preco_meia_centavos=sessao.preco_meia_centavos,
    )


async def buscar_sessao(db: AsyncSession, sessao_id: int) -> Sessao:
    sessao = await db.get(Sessao, sessao_id)
    if sessao is None:
        raise HTTPException(404, "Sessão não encontrada")
    return sessao


# As respostas abaixo vêm do cache: o JSON pronto, sem passar pelo banco, pelo
# cinema nem pela conversão. As funções "montar_" só rodam quando a cópia não existe.


async def montar_filmes(db: AsyncSession) -> bytes:
    filmes = (await db.scalars(select(Filme).order_by(Filme.id))).all()
    return LISTA_DE_FILMES.dump_json([FilmeOut.model_validate(f) for f in filmes])


async def montar_sessoes(db: AsyncSession, filme_id: int | None) -> bytes:
    consulta = select(Sessao).order_by(Sessao.inicio)
    if filme_id is not None:
        consulta = consulta.where(Sessao.filme_id == filme_id)
    return LISTA_DE_SESSOES.dump_json([await para_sessao_out(s) for s in (await db.scalars(consulta)).all()])


async def montar_mapa(db: AsyncSession, sessao_id: int) -> bytes:
    await buscar_sessao(db, sessao_id)
    assentos = await clients.buscar_mapa(sessao_id)
    mapa = MapaDeAssentosOut(
        sessao_id=sessao_id,
        livres=sum(1 for a in assentos if a["status"] == "livre"),
        assentos=assentos,
    )
    return mapa.model_dump_json().encode()


def json_pronto(conteudo: bytes) -> Response:
    return Response(conteudo, media_type="application/json")


@router.get("/filmes", response_model=list[FilmeOut])
async def listar_filmes(db: AsyncSession = Depends(get_db)):
    return json_pronto(await cache.resposta_pronta("filmes", PROGRAMACAO_TTL_S, lambda: montar_filmes(db)))


@router.get("/sessoes", response_model=list[SessaoOut])
async def listar_sessoes(filme_id: int | None = None, db: AsyncSession = Depends(get_db)):
    chave = f"sessoes:filme:{filme_id}"
    return json_pronto(await cache.resposta_pronta(chave, PROGRAMACAO_TTL_S, lambda: montar_sessoes(db, filme_id)))


@router.get("/sessoes/{sessao_id}", response_model=SessaoOut)
async def detalhar_sessao(sessao_id: int, db: AsyncSession = Depends(get_db)):
    return await para_sessao_out(await buscar_sessao(db, sessao_id))


@router.get("/sessoes/{sessao_id}/assentos", response_model=MapaDeAssentosOut)
async def mapa_de_assentos(sessao_id: int, db: AsyncSession = Depends(get_db)):
    # O mapa é apagado do cache sempre que uma compra mexe nos assentos da sessão
    # (app/compra.py). A validade curta cobre o resto: vendas feitas por outros
    # canais, como a bilheteria do cinema.
    return json_pronto(await cache.resposta_pronta(cache.chave_do_mapa(sessao_id), MAPA_TTL_S, lambda: montar_mapa(db, sessao_id)))


@router.get("/sessoes/{sessao_id}/resumo", response_model=ResumoSessaoOut)
async def resumo_de_vendas(sessao_id: int, db: AsyncSession = Depends(get_db)):
    sessao = await buscar_sessao(db, sessao_id)
    sala = await sessao.awaitable_attrs.sala
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
        capacidade=sala.capacidade,
        ingressos_vendidos=vendidos,
        meia_vendidas=meia,
        cota_meia=sala.capacidade * COTA_MEIA_ENTRADA_PCT // 100,
        maior_compra_por_cpf=maior_compra,
    )

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cache, clients
from app.config import COTA_MEIA_ENTRADA_PCT, FUSO_HORARIO, MAPA_TTL_S, PROGRAMACAO_TTL_S
from app.db import get_db
from app.models import Filme, Ingresso, Pedido, Sessao
from app.schemas import FilmeOut, MapaDeAssentosOut, ResumoSessaoOut, SessaoOut

# As rotas são "def" (síncronas): o FastAPI roda cada uma numa thread de um
# pool com 40 threads. Com 40 requisições lentas ao mesmo tempo, a 41ª espera.
router = APIRouter(tags=["catálogo"])

LISTA_DE_FILMES = TypeAdapter(list[FilmeOut])
LISTA_DE_SESSOES = TypeAdapter(list[SessaoOut])


def para_sessao_out(sessao: Sessao) -> SessaoOut:
    # ⚠️ PROPOSITAL: cada .filme e .sala abaixo dispara uma consulta
    # extra no banco (problema N+1).
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


def buscar_sessao(db: Session, sessao_id: int) -> Sessao:
    sessao = db.get(Sessao, sessao_id)
    if sessao is None:
        raise HTTPException(404, "Sessão não encontrada")
    return sessao


# As respostas abaixo vêm do cache: o JSON pronto, sem passar pelo banco, pelo
# cinema nem pela conversão. As funções "montar_" só rodam quando a cópia não existe.


def montar_filmes(db: Session) -> bytes:
    filmes = db.scalars(select(Filme).order_by(Filme.id)).all()
    return LISTA_DE_FILMES.dump_json([FilmeOut.model_validate(f) for f in filmes])


def montar_sessoes(db: Session, filme_id: int | None) -> bytes:
    consulta = select(Sessao).order_by(Sessao.inicio)
    if filme_id is not None:
        consulta = consulta.where(Sessao.filme_id == filme_id)
    return LISTA_DE_SESSOES.dump_json([para_sessao_out(s) for s in db.scalars(consulta).all()])


def montar_mapa(db: Session, sessao_id: int) -> bytes:
    buscar_sessao(db, sessao_id)
    assentos = clients.buscar_mapa(sessao_id)
    mapa = MapaDeAssentosOut(
        sessao_id=sessao_id,
        livres=sum(1 for a in assentos if a["status"] == "livre"),
        assentos=assentos,
    )
    return mapa.model_dump_json().encode()


def json_pronto(conteudo: bytes) -> Response:
    return Response(conteudo, media_type="application/json")


@router.get("/filmes", response_model=list[FilmeOut])
def listar_filmes(db: Session = Depends(get_db)):
    return json_pronto(cache.resposta_pronta("filmes", PROGRAMACAO_TTL_S, lambda: montar_filmes(db)))


@router.get("/sessoes", response_model=list[SessaoOut])
def listar_sessoes(filme_id: int | None = None, db: Session = Depends(get_db)):
    chave = f"sessoes:filme:{filme_id}"
    return json_pronto(cache.resposta_pronta(chave, PROGRAMACAO_TTL_S, lambda: montar_sessoes(db, filme_id)))


@router.get("/sessoes/{sessao_id}", response_model=SessaoOut)
def detalhar_sessao(sessao_id: int, db: Session = Depends(get_db)):
    return para_sessao_out(buscar_sessao(db, sessao_id))


@router.get("/sessoes/{sessao_id}/assentos", response_model=MapaDeAssentosOut)
def mapa_de_assentos(sessao_id: int, db: Session = Depends(get_db)):
    # O mapa é apagado do cache sempre que uma compra mexe nos assentos da sessão
    # (app/compra.py). A validade curta cobre o resto: vendas feitas por outros
    # canais, como a bilheteria do cinema.
    return json_pronto(cache.resposta_pronta(cache.chave_do_mapa(sessao_id), MAPA_TTL_S, lambda: montar_mapa(db, sessao_id)))


@router.get("/sessoes/{sessao_id}/resumo", response_model=ResumoSessaoOut)
def resumo_de_vendas(sessao_id: int, db: Session = Depends(get_db)):
    sessao = buscar_sessao(db, sessao_id)
    vendidos = db.scalar(select(func.count(Ingresso.id)).where(Ingresso.sessao_id == sessao_id))
    meia = db.scalar(select(func.count(Ingresso.id)).where(Ingresso.sessao_id == sessao_id, Ingresso.tipo == "meia"))
    por_cpf = (
        select(func.count(Ingresso.id).label("quantidade"))
        .join(Pedido)
        .where(Ingresso.sessao_id == sessao_id)
        .group_by(Pedido.cpf)
        .subquery()
    )
    maior_compra = db.scalar(select(func.coalesce(func.max(por_cpf.c.quantidade), 0)))
    return ResumoSessaoOut(
        sessao_id=sessao_id,
        capacidade=sessao.sala.capacidade,
        ingressos_vendidos=vendidos,
        meia_vendidas=meia,
        cota_meia=sessao.sala.capacidade * COTA_MEIA_ENTRADA_PCT // 100,
        maior_compra_por_cpf=maior_compra,
    )

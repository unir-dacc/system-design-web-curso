"""
As rotas: as mesmas e com as mesmas respostas das outras etapas.

Sem framework: um roteador pequeno escolhe a função pela rota, e cada função
devolve (status, corpo em bytes). É o que o FastAPI faz por baixo, sem a
validação, a injeção de dependências e o middleware de cada requisição.
"""

from collections.abc import Awaitable, Callable
from datetime import timezone
from typing import Any
from urllib.parse import parse_qs

import msgspec

from app import banco, cache, clientes, compra, notificacoes
from app.config import COTA_MEIA_ENTRADA_PCT, FUSO_HORARIO, MAPA_TTL_S, PROGRAMACAO_TTL_S
from app.erros import AssentosIndisponiveis, AssentosInexistentes, ErroHTTP, PagamentoNaoConcluido
from app.modelos import FilmeOut, IngressoOut, MapaOut, PedidoOut, SessaoOut, json_encoder, pedido_decoder

JSON = "application/json"
Resposta = tuple[int, bytes, str]


def json(status: int, corpo: Any) -> Resposta:
    return status, json_encoder.encode(corpo), JSON


def para_sessao_out(s: banco.Sessao) -> SessaoOut:
    return SessaoOut(s.id, s.filme_id, s.filme, s.cinema, s.sala, s.inicio.astimezone(FUSO_HORARIO).isoformat(),
                     s.preco_inteira_centavos, s.preco_meia_centavos)


def numero(valor: str, nome: str) -> int:
    if not valor.isdigit():
        raise ErroHTTP(422, f"{nome} precisa ser um número")
    return int(valor)


# --- Catálogo ---
# As respostas abaixo vêm do cache: o JSON pronto. As funções "montar" só
# rodam quando a cópia não existe.


async def listar_filmes(query: str) -> Resposta:
    async def montar() -> bytes:
        linhas = await banco.pool.fetch("SELECT id, titulo, duracao_min, classificacao, sinopse FROM filmes ORDER BY id")
        return json_encoder.encode([FilmeOut(*linha) for linha in linhas])

    return 200, await cache.resposta_pronta("filmes", PROGRAMACAO_TTL_S, montar), JSON


async def listar_sessoes(query: str) -> Resposta:
    filme_id = parse_qs(query).get("filme_id", [""])[0]

    async def montar() -> bytes:
        if filme_id:
            consulta = banco.SELECIONAR_SESSOES + " WHERE s.filme_id = $1 ORDER BY s.inicio"
            linhas = await banco.pool.fetch(consulta, numero(filme_id, "filme_id"))
        else:
            linhas = await banco.pool.fetch(banco.SELECIONAR_SESSOES + " ORDER BY s.inicio")
        return json_encoder.encode([para_sessao_out(banco.Sessao(linha)) for linha in linhas])

    chave = "sessoes:filme:" + (filme_id or "None")
    return 200, await cache.resposta_pronta(chave, PROGRAMACAO_TTL_S, montar), JSON


async def buscar_sessao(sessao_id: int) -> banco.Sessao:
    sessao = await banco.buscar_sessao(sessao_id)
    if sessao is None:
        raise ErroHTTP(404, "Sessão não encontrada")
    return sessao


async def detalhar_sessao(sessao_id: int) -> Resposta:
    return json(200, para_sessao_out(await buscar_sessao(sessao_id)))


async def mapa_de_assentos(sessao_id: int) -> Resposta:
    """O mapa é apagado do cache sempre que uma compra mexe nos assentos da sessão.
    A validade curta cobre o resto: vendas feitas por outros canais."""

    async def montar() -> bytes:
        await buscar_sessao(sessao_id)
        assentos = await clientes.buscar_mapa(sessao_id)
        livres = sum(1 for a in assentos if a.status == "livre")
        return json_encoder.encode(MapaOut(sessao_id, livres, assentos))

    return 200, await cache.resposta_pronta(cache.chave_do_mapa(sessao_id), MAPA_TTL_S, montar), JSON


async def resumo_de_vendas(sessao_id: int) -> Resposta:
    sessao = await buscar_sessao(sessao_id)
    linha = await banco.pool.fetchrow(
        """SELECT
             (SELECT count(*) FROM ingressos WHERE sessao_id = $1),
             (SELECT count(*) FROM ingressos WHERE sessao_id = $1 AND tipo = 'meia'),
             (SELECT coalesce(max(q), 0) FROM (
                SELECT count(i.id) AS q FROM ingressos i JOIN pedidos p ON p.id = i.pedido_id
                WHERE i.sessao_id = $1 GROUP BY p.cpf) por_cpf)""",
        sessao_id,
    )
    return json(200, {
        "sessao_id": sessao_id, "capacidade": sessao.capacidade, "ingressos_vendidos": linha[0], "meia_vendidas": linha[1],
        "cota_meia": sessao.capacidade * COTA_MEIA_ENTRADA_PCT // 100, "maior_compra_por_cpf": linha[2],
    })


# --- Pedidos e ingressos ---


def para_ingresso_out(linha: Any) -> IngressoOut:
    return IngressoOut(linha[0], linha[1], linha[2], linha[3], f"/ingressos/{linha[0]}/qrcode")


async def para_pedido_out(p: Any) -> PedidoOut:
    linhas = await banco.pool.fetch(
        "SELECT codigo, assento, tipo, preco_centavos FROM ingressos WHERE pedido_id = $1 ORDER BY id", p.id
    )
    return PedidoOut(p.id, p.sessao_id, p.nome, p.email, p.status, p.subtotal_centavos, p.taxa_centavos,
                     p.total_centavos, p.criado_em.astimezone(timezone.utc).isoformat(),
                     [para_ingresso_out(linha) for linha in linhas])


async def criar_pedido(corpo: bytes) -> Resposta:
    """201 = compra concluída: cobrada, confirmada e com os ingressos emitidos."""
    try:
        dados = pedido_decoder.decode(corpo)
    except msgspec.DecodeError as erro:
        raise ErroHTTP(422, str(erro))
    try:
        pedido = await compra.realizar_compra(dados)
    except PagamentoNaoConcluido as erro:
        return json(erro.status, {"detail": erro.detalhe, "pedido": await para_pedido_out(erro.pedido)})
    except AssentosIndisponiveis as erro:
        raise ErroHTTP(409, {"mensagem": "Assentos indisponíveis", "indisponiveis": erro.assentos})
    except AssentosInexistentes as erro:
        raise ErroHTTP(422, f"Assentos inexistentes: {erro.assentos}")
    return json(201, await para_pedido_out(pedido))


async def detalhar_pedido(pedido_id: int) -> Resposta:
    linha = await banco.pool.fetchrow(
        """SELECT id, sessao_id, nome, email, status, subtotal_centavos, taxa_centavos, total_centavos, criado_em
           FROM pedidos WHERE id = $1""",
        pedido_id,
    )
    if linha is None:
        raise ErroHTTP(404, "Pedido não encontrado")
    pedido = compra.Pedido(linha[1], linha[2], "", linha[3], linha[5], linha[6], 0, 0)
    pedido.id, pedido.status, pedido.criado_em = linha[0], linha[4], linha[8]
    return json(200, await para_pedido_out(pedido))


async def buscar_ingresso(codigo: str) -> IngressoOut:
    linha = await banco.pool.fetchrow("SELECT codigo, assento, tipo, preco_centavos FROM ingressos WHERE codigo = $1", codigo)
    if linha is None:
        raise ErroHTTP(404, "Ingresso não encontrado")
    return para_ingresso_out(linha)


async def detalhar_ingresso(codigo: str) -> Resposta:
    return json(200, await buscar_ingresso(codigo))


async def qrcode_do_ingresso(codigo: str) -> Resposta:
    ingresso = await buscar_ingresso(codigo)
    return 200, notificacoes.gerar_qrcode_png(ingresso.codigo), "image/png"


# --- Apoio às aulas (não existiriam em produção) ---


async def reset() -> Resposta:
    await banco.pool.execute("TRUNCATE ingressos, pedidos RESTART IDENTITY")
    # Zera as estatísticas de cada consulta (pg_stat_statements): depois do
    # teste, o pgHero mostra só a rodada
    await banco.pool.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    await banco.pool.execute("SELECT pg_stat_statements_reset()")
    await cache.r.flushdb()
    return json(200, {"status": "pedidos, ingressos e cache apagados"})


async def rotear(metodo: str, caminho: str, query: str, ler_corpo: Callable[[], Awaitable[bytes]]) -> Resposta:
    """Escolhe a função pela rota. Devolve (status, corpo, tipo do conteúdo)."""
    partes = caminho.strip("/").split("/")
    n = len(partes)
    try:
        if metodo == "GET":
            if caminho == "/health":
                return json(200, {"status": "ok"})
            if caminho == "/filmes":
                return await listar_filmes(query)
            if partes[0] == "sessoes":
                if n == 1:
                    return await listar_sessoes(query)
                sessao_id = numero(partes[1], "sessao_id")
                if n == 2:
                    return await detalhar_sessao(sessao_id)
                if n == 3 and partes[2] == "assentos":
                    return await mapa_de_assentos(sessao_id)
                if n == 3 and partes[2] == "resumo":
                    return await resumo_de_vendas(sessao_id)
            if partes[0] == "pedidos" and n == 2:
                return await detalhar_pedido(numero(partes[1], "pedido_id"))
            if partes[0] == "ingressos" and n == 2:
                return await detalhar_ingresso(partes[1])
            if partes[0] == "ingressos" and n == 3 and partes[2] == "qrcode":
                return await qrcode_do_ingresso(partes[1])
        elif metodo == "POST":
            if caminho == "/pedidos":
                return await criar_pedido(await ler_corpo())
            if caminho == "/admin/reset":
                return await reset()
        return json(404, {"detail": "Not Found"})
    except ErroHTTP as erro:
        return json(erro.status, {"detail": erro.detail})

"""
O banco, com SQL escrito à mão (asyncpg), sem ORM.

O ORM transforma cada linha num objeto Python cheio de controle (o que mudou,
o que falta carregar), e isso custa CPU em toda consulta. Aqui cada consulta
é o SQL direto, e cada linha volta como uma tupla. As tabelas e as consultas
são as mesmas da etapa em Go.
"""

import json
from datetime import datetime
from typing import Any

import asyncpg

from app.config import DATABASE_URL, DB_POOL, SEED_PATH

# Preenchido por conectar(), na primeira requisição
pool: Any = None

ESQUEMA = """
CREATE TABLE IF NOT EXISTS filmes (
    id integer PRIMARY KEY,
    titulo varchar NOT NULL,
    duracao_min integer NOT NULL,
    classificacao varchar(2) NOT NULL,
    sinopse varchar NOT NULL
);
CREATE TABLE IF NOT EXISTS cinemas (
    id integer PRIMARY KEY,
    nome varchar NOT NULL
);
CREATE TABLE IF NOT EXISTS salas (
    id integer PRIMARY KEY,
    cinema_id integer NOT NULL REFERENCES cinemas(id),
    nome varchar NOT NULL,
    capacidade integer NOT NULL
);
CREATE TABLE IF NOT EXISTS sessoes (
    id integer PRIMARY KEY,
    filme_id integer NOT NULL REFERENCES filmes(id),
    sala_id integer NOT NULL REFERENCES salas(id),
    inicio timestamptz NOT NULL,
    preco_inteira_centavos integer NOT NULL
);
CREATE TABLE IF NOT EXISTS pedidos (
    id serial PRIMARY KEY,
    sessao_id integer NOT NULL REFERENCES sessoes(id),
    nome varchar NOT NULL,
    cpf varchar(11) NOT NULL,
    email varchar NOT NULL,
    -- reservando -> aguardando_pagamento -> confirmado | pagamento_recusado | pagamento_falhou | cancelado
    status varchar NOT NULL,
    subtotal_centavos integer NOT NULL,
    taxa_centavos integer NOT NULL,
    total_centavos integer NOT NULL,
    -- Pedidos em andamento também contam para o limite por CPF e para a cota de meia
    qtd_ingressos integer NOT NULL,
    qtd_meia integer NOT NULL,
    reserva_id varchar,
    cobranca_id varchar,
    criado_em timestamptz NOT NULL DEFAULT now()
);
-- Toda compra soma os pedidos da sessão e do CPF (limite por CPF e cota de meia)
CREATE INDEX IF NOT EXISTS ix_pedidos_sessao_cpf ON pedidos (sessao_id, cpf);

CREATE TABLE IF NOT EXISTS ingressos (
    id serial PRIMARY KEY,
    pedido_id integer NOT NULL REFERENCES pedidos(id),
    sessao_id integer NOT NULL REFERENCES sessoes(id),
    assento varchar(4) NOT NULL,
    tipo varchar(7) NOT NULL,
    preco_centavos integer NOT NULL,
    codigo varchar(32) NOT NULL UNIQUE,
    criado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_ingressos_pedido_id ON ingressos (pedido_id);  -- os ingressos de um pedido
CREATE INDEX IF NOT EXISTS ix_ingressos_sessao_id ON ingressos (sessao_id);  -- os ingressos de uma sessão
"""


async def conectar() -> None:
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=DB_POOL)


async def preparar() -> None:
    """Cria as tabelas e carrega o catálogo. Os backends sobem ao mesmo tempo:
    a trava do banco faz um de cada vez; os outros encontram tudo pronto."""
    async with pool.acquire() as conexao, conexao.transaction():
        await conexao.execute("SELECT pg_advisory_xact_lock(0)")
        await conexao.execute(ESQUEMA)
        if await conexao.fetchval("SELECT count(*) FROM filmes") == 0:
            await carregar_catalogo(conexao)


async def carregar_catalogo(conexao: Any) -> None:
    """Popula filmes, cinemas, salas e sessões a partir do mesmo arquivo usado pelo sistema do cinema."""
    with open(SEED_PATH, encoding="utf-8") as arquivo:
        c = json.load(arquivo)
    await conexao.executemany(
        "INSERT INTO filmes VALUES ($1, $2, $3, $4, $5)",
        [(f["id"], f["titulo"], f["duracao_min"], f["classificacao"], f["sinopse"]) for f in c["filmes"]],
    )
    await conexao.executemany("INSERT INTO cinemas VALUES ($1, $2)", [(ci["id"], ci["nome"]) for ci in c["cinemas"]])
    await conexao.executemany(
        "INSERT INTO salas VALUES ($1, $2, $3, $4)",
        [(s["id"], s["cinema_id"], s["nome"], len(s["fileiras"]) * s["assentos_por_fileira"]) for s in c["salas"]],
    )
    await conexao.executemany(
        "INSERT INTO sessoes VALUES ($1, $2, $3, $4, $5)",
        [
            (s["id"], s["filme_id"], s["sala_id"], datetime.fromisoformat(s["inicio"]), s["preco_inteira_centavos"])
            for s in c["sessoes"]
        ],
    )


class Sessao:
    def __init__(self, linha: Any) -> None:
        self.id: int = linha[0]
        self.filme_id: int = linha[1]
        self.filme: str = linha[2]
        self.cinema: str = linha[3]
        self.sala: str = linha[4]
        self.inicio: datetime = linha[5]
        self.preco_inteira_centavos: int = linha[6]
        self.capacidade: int = linha[7]

    @property
    def preco_meia_centavos(self) -> int:
        return self.preco_inteira_centavos // 2


# Sala, filme e cinema vêm na mesma consulta da sessão
SELECIONAR_SESSOES = """
SELECT s.id, s.filme_id, f.titulo, c.nome, sa.nome, s.inicio, s.preco_inteira_centavos, sa.capacidade
FROM sessoes s
JOIN filmes f ON f.id = s.filme_id
JOIN salas sa ON sa.id = s.sala_id
JOIN cinemas c ON c.id = sa.cinema_id"""


async def buscar_sessao(sessao_id: int) -> Sessao | None:
    linha = await pool.fetchrow(SELECIONAR_SESSOES + " WHERE s.id = $1", sessao_id)
    return Sessao(linha) if linha is not None else None

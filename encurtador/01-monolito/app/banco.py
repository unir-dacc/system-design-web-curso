"""
A tabela de links e os links que já existem quando a aula começa.

O código curto de cada link vem do número dele (o id), codificado pelo Sqids
(https://sqids.org), uma biblioteca muito usada para isso: o link 1 vira algo
como "Fnu8P51", e não "1". Assim ninguém adivinha os links dos outros contando
1, 2, 3... O Sqids nunca leva dois números ao mesmo código, então não é
preciso conferir no banco se o código já existe.

Não é criptografia: o alfabeto embaralhado (app/config.py) funciona como um
segredo leve, que dificulta, mas não impede, descobrir o padrão.
"""

from datetime import datetime, timedelta, timezone

from sqids import Sqids
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import ALFABETO_DOS_CODIGOS, LINKS_INICIAIS, TAMANHO_DO_CODIGO

sqids = Sqids(alphabet=ALFABETO_DOS_CODIGOS, min_length=TAMANHO_DO_CODIGO)

ESQUEMA = """
CREATE SEQUENCE IF NOT EXISTS links_id_seq;

CREATE TABLE IF NOT EXISTS links (
    id bigint PRIMARY KEY DEFAULT nextval('links_id_seq'),
    -- ⚠️ PROPOSITAL: sem índice em "codigo". Todo redirecionamento procura o
    -- link pelo código, e sem índice o Postgres lê a tabela inteira.
    codigo varchar(12) NOT NULL,
    url text NOT NULL,
    cliques bigint NOT NULL DEFAULT 0,
    criado_em timestamptz NOT NULL DEFAULT now()
);
"""


def codigo_do_link(id_do_link: int) -> str:
    return sqids.encode([id_do_link])


def preparar(conexao: Connection) -> None:
    """Cria a tabela e, na primeira vez, os links que já existem quando a aula começa."""
    conexao.execute(text(ESQUEMA))
    if conexao.scalar(text("SELECT count(*) FROM (SELECT 1 FROM links LIMIT 1) t")):
        return

    # COPY: o jeito mais rápido de colocar muitas linhas no Postgres de uma vez
    agora = datetime.now(timezone.utc)
    cursor = conexao.connection.dbapi_connection.cursor()
    with cursor.copy("COPY links (id, codigo, url, criado_em) FROM STDIN") as copia:
        for n in range(1, LINKS_INICIAIS + 1):
            copia.write_row((n, codigo_do_link(n), f"https://exemplo.com/pagina/{n}", agora - timedelta(days=n % 365)))
    conexao.execute(text("SELECT setval('links_id_seq', :ultimo)"), {"ultimo": LINKS_INICIAIS})
    # Atualiza as estatísticas que o Postgres usa para planejar as consultas
    conexao.execute(text("ANALYZE links"))

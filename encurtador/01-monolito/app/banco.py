"""
A tabela de links e os links que já existem quando a aula começa.

O código curto de cada link vem do número dele (o id), embaralhado e escrito
em base 62 (0-9, a-z, A-Z), com 7 caracteres: o link 1 vira algo como
"0dB7xQ2", e não "1". Assim ninguém adivinha os links dos outros contando
1, 2, 3... O embaralhamento é uma multiplicação que nunca leva dois números
ao mesmo resultado: cada id tem um código só, e nunca há dois links com o
mesmo código. Não é preciso conferir no banco se o código já existe.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import LINKS_INICIAIS

ESQUEMA = """
CREATE SEQUENCE IF NOT EXISTS links_id_seq;

CREATE TABLE IF NOT EXISTS links (
    id bigint PRIMARY KEY DEFAULT nextval('links_id_seq'),
    -- ⚠️ PROPOSITAL: sem índice em "codigo". Todo redirecionamento procura o
    -- link pelo código, e sem índice o Postgres lê a tabela inteira.
    codigo varchar(7) NOT NULL,
    url text NOT NULL,
    cliques bigint NOT NULL DEFAULT 0,
    criado_em timestamptz NOT NULL DEFAULT now()
);

-- 62^7 = 3.521.614.606.208 códigos possíveis. 2654435761 não tem fator em
-- comum com 62^7, então multiplicar por ele embaralha sem repetir.
CREATE OR REPLACE FUNCTION codigo_curto(n bigint) RETURNS text AS $$
DECLARE
    alfabeto constant text := '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';
    x bigint := (n * 2654435761) % 3521614606208;
    codigo text := '';
BEGIN
    FOR i IN 1..7 LOOP
        codigo := substr(alfabeto, (x % 62)::int + 1, 1) || codigo;
        x := x / 62;
    END LOOP;
    RETURN codigo;
END
$$ LANGUAGE plpgsql IMMUTABLE;
"""


def preparar(conexao: Connection) -> None:
    """Cria a tabela e, na primeira vez, os links que já existem quando a aula começa."""
    conexao.execute(text(ESQUEMA))
    if conexao.scalar(text("SELECT count(*) FROM (SELECT 1 FROM links LIMIT 1) t")):
        return
    conexao.execute(
        text(
            "INSERT INTO links (id, codigo, url, criado_em) "
            "SELECT n, codigo_curto(n), 'https://exemplo.com/pagina/' || n, now() - (n % 365) * interval '1 day' "
            "FROM generate_series(1, :quantidade) AS n"
        ),
        {"quantidade": LINKS_INICIAIS},
    )
    conexao.execute(text("SELECT setval('links_id_seq', :ultimo)"), {"ultimo": LINKS_INICIAIS})
    # Atualiza as estatísticas que o Postgres usa para planejar as consultas
    conexao.execute(text("ANALYZE links"))

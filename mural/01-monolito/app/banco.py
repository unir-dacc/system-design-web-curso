"""
A rede que já existe quando a aula começa, criada na primeira subida.

Uma rede de verdade é desigual, e a carga inicial também:
- cada usuário segue de 1 a 300 pessoas (a maioria segue poucas);
- quem é seguido sai de uma distribuição muito concentrada nos primeiros
  usuários: eles são as CELEBRIDADES, com dezenas de milhares de seguidores,
  enquanto a maioria tem um punhado;
- as celebridades também postam mais, e poucos posts concentram as curtidas.

Tudo é gerado pelo próprio Postgres (generate_series), que é bem mais rápido
do que mandar milhões de linhas pelo Python.
"""

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import COMENTARIOS_INICIAIS, CURTIDAS_INICIAIS, POSTS_INICIAIS, USUARIOS_INICIAIS
from app.modelos import Base

# Quando a carga inicial terminou: tudo o que for criado depois disso é da aula,
# e é apagado no reset (app/routes/admin.py)
AULA = "CREATE TABLE IF NOT EXISTS aula (preparada_em timestamptz NOT NULL)"

NOMES = "ARRAY['Ana','Bruno','Carla','Diego','Elisa','Felipe','Gabi','Heitor','Iara','João','Karina','Lucas','Marina','Nina','Otávio','Paula','Rafael','Sofia','Tiago','Vitória']"
SOBRENOMES = "ARRAY['Silva','Souza','Oliveira','Santos','Lima','Pereira','Costa','Rocha','Alves','Gomes','Martins','Araújo','Ribeiro','Barbosa','Cardoso']"
LOREM = (
    "Hoje o dia foi longo, mas valeu a pena. Alguém mais acha que segunda-feira devia ser opcional? "
    "Acabei de ver o pôr do sol mais bonito do ano e precisava contar para alguém. Café, código e chuva: "
    "a combinação perfeita. Quem vai no show sábado? Dica do dia: beba água e faça backup. Não acredito "
    "que terminei aquele livro, que final! Rodei o teste de carga e o servidor pediu socorro. Bom dia, mural!"
)

CARGA = [
    f"""
    INSERT INTO usuarios (id, nome, criado_em)
    SELECT g,
           ({NOMES})[1 + floor(random() * 20)::int] || ' ' || ({SOBRENOMES})[1 + floor(random() * 15)::int],
           :agora - random() * interval '3 years'
    FROM generate_series(1, :usuarios) g
    """,
    # Quantos cada um segue: de 1 a 300, a maioria poucos. Quem é seguido:
    # random()^4 empurra o sorteio para os primeiros ids, as celebridades.
    """
    INSERT INTO seguidores (seguidor_id, seguido_id)
    SELECT seguidor, seguido FROM (
        SELECT u AS seguidor, 1 + floor(:usuarios * power(random(), 4))::bigint AS seguido
        FROM generate_series(1, :usuarios) u
        CROSS JOIN LATERAL generate_series(1, floor(exp(random() * ln(300)))::int + 0 * u)
    ) sorteio
    WHERE seguidor <> seguido
    ON CONFLICT DO NOTHING
    """,
    """
    INSERT INTO posts (id, autor_id, texto, criado_em)
    SELECT g,
           1 + floor(:usuarios * power(random(), 2))::bigint,
           substr(:lorem, 1 + floor(random() * 200)::int, 60 + floor(random() * 140)::int),
           :agora - random() * interval '365 days'
    FROM generate_series(1, :posts) g
    """,
    """
    INSERT INTO curtidas (post_id, usuario_id, criado_em)
    SELECT 1 + floor(:posts * power(random(), 3))::bigint,
           1 + floor(:usuarios * random())::bigint,
           :agora - random() * interval '365 days'
    FROM generate_series(1, :curtidas)
    ON CONFLICT DO NOTHING
    """,
    """
    INSERT INTO comentarios (id, post_id, autor_id, texto, criado_em)
    SELECT g,
           1 + floor(:posts * power(random(), 3))::bigint,
           1 + floor(:usuarios * random())::bigint,
           substr(:lorem, 1 + floor(random() * 300)::int, 20 + floor(random() * 60)::int),
           :agora - random() * interval '365 days'
    FROM generate_series(1, :comentarios) g
    """,
    "SELECT setval(pg_get_serial_sequence('usuarios', 'id'), :usuarios)",
    "SELECT setval(pg_get_serial_sequence('posts', 'id'), :posts)",
    "SELECT setval(pg_get_serial_sequence('comentarios', 'id'), :comentarios)",
    "INSERT INTO aula (preparada_em) VALUES (:agora)",
    # Atualiza as estatísticas que o Postgres usa para planejar as consultas
    "ANALYZE",
]


def preparar(conexao: Connection) -> None:
    """Cria as tabelas e, na primeira subida, a rede que já existe quando a aula começa."""
    Base.metadata.create_all(conexao)
    conexao.execute(text(AULA))
    if conexao.scalar(text("SELECT count(*) FROM aula")):
        return
    parametros = {
        "agora": datetime.now(timezone.utc),
        "usuarios": USUARIOS_INICIAIS,
        "posts": POSTS_INICIAIS,
        "curtidas": CURTIDAS_INICIAIS,
        "comentarios": COMENTARIOS_INICIAIS,
        "lorem": LOREM,
    }
    for instrucao in CARGA:
        conexao.execute(text(instrucao), parametros)

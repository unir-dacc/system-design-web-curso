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
from sqlalchemy.schema import CreateTable
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

# O total de curtidas de cada post, contado a partir das curtidas que já existem
TOTAIS_DE_CURTIDAS = """
    UPDATE posts SET curtidas = total.curtidas
    FROM (SELECT post_id, count(*) AS curtidas FROM curtidas GROUP BY post_id) total
    WHERE posts.id = total.post_id
"""

CARGA = [
    # Durante a carga, o banco não confere as ForeignKeys linha a linha (são
    # milhões de conferências): os dados gerados aqui já são válidos
    "SET LOCAL session_replication_role = replica",
    f"""
    INSERT INTO usuarios (id, nome, criado_em)
    SELECT g,
           ({NOMES})[1 + floor(random() * 20)::int] || ' ' || ({SOBRENOMES})[1 + floor(random() * 15)::int],
           :agora - random() * interval '3 years'
    FROM generate_series(1, :usuarios) g
    """,
    # Quantos cada um segue: de 1 a 300, a maioria poucos. Quem é seguido:
    # random()^4 empurra o sorteio para os primeiros ids, as celebridades.
    # Os pares repetidos do sorteio ficam de fora (DISTINCT), e a inserção vai
    # na ordem da chave primária, bem mais rápida do que em ordem aleatória.
    """
    INSERT INTO seguidores (seguidor_id, seguido_id)
    SELECT DISTINCT seguidor, seguido FROM (
        SELECT u AS seguidor, 1 + floor(:usuarios * power(random(), 4))::bigint AS seguido
        FROM generate_series(1, :usuarios) u
        CROSS JOIN LATERAL generate_series(1, floor(exp(random() * ln(300)))::int + 0 * u)
    ) sorteio
    WHERE seguidor <> seguido
    ORDER BY 1, 2
    """,
    """
    INSERT INTO posts (id, autor_id, texto, criado_em)
    SELECT g,
           1 + floor(:usuarios * power(random(), 2))::bigint,
           substr(:lorem, 1 + floor(random() * 200)::int, 60 + floor(random() * 140)::int),
           :agora - random() * interval '365 days'
    FROM generate_series(1, :posts) g
    """,
    # Do mesmo jeito: sem os pares repetidos, na ordem da chave primária
    """
    INSERT INTO curtidas (post_id, usuario_id, criado_em)
    SELECT post_id, usuario_id, min(criado_em) FROM (
        SELECT 1 + floor(:posts * power(random(), 3))::bigint AS post_id,
               1 + floor(:usuarios * random())::bigint AS usuario_id,
               :agora - random() * interval '365 days' AS criado_em
        FROM generate_series(1, :curtidas)
    ) sorteio
    GROUP BY 1, 2
    ORDER BY 1, 2
    """,
    # O total de curtidas de cada post, guardado no próprio post
    TOTAIS_DE_CURTIDAS,
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
    "SET LOCAL session_replication_role = DEFAULT",
    # Atualiza as estatísticas que o Postgres usa para planejar as consultas
    "ANALYZE",
]


def preparar(conexao: Connection) -> bool:
    """Cria as tabelas, a rede que já existe quando a aula começa e os índices.

    Se o banco já tem a rede da etapa 01, aproveita: só acrescenta o que esta
    etapa tem a mais (o total de curtidas nos posts e os índices). Devolve se
    precisou reescrever os posts (na carga ou ao acrescentar o total).
    """
    mexeu = False
    # As estatísticas de cada consulta (o pg_stat_statements do docker-compose.yml)
    conexao.execute(text("CREATE EXTENSION IF NOT EXISTS pg_stat_statements"))
    # As tabelas primeiro, sem os índices de app/modelos.py (create_all criaria
    # os dois juntos)
    for tabela in Base.metadata.sorted_tables:
        conexao.execute(CreateTable(tabela, if_not_exists=True))
    conexao.execute(text(AULA))
    if not conexao.scalar(text("SELECT count(*) FROM aula")):
        carregar_rede_inicial(conexao)
        mexeu = True
    # Vindo da etapa 01, a rede já existe, mas a tabela de posts ainda não tem o
    # total de curtidas: acrescenta a coluna e conta o que já está lá
    tem_o_total = conexao.scalar(text(
        "SELECT count(*) FROM information_schema.columns WHERE table_name = 'posts' AND column_name = 'curtidas'"
    ))
    if not tem_o_total:
        conexao.execute(text("ALTER TABLE posts ADD COLUMN curtidas integer NOT NULL DEFAULT 0"))
        conexao.execute(text(TOTAIS_DE_CURTIDAS))
        mexeu = True
    # Depois da carga: encher a tabela sem índice e criar o índice no fim é bem
    # mais rápido do que atualizar o índice a cada linha inserida
    for tabela in Base.metadata.sorted_tables:
        for indice in tabela.indexes:
            indice.create(conexao, checkfirst=True)
    return mexeu


def carregar_rede_inicial(conexao: Connection) -> None:
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

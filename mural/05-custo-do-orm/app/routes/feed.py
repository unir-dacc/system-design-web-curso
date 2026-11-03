from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import POSTS_POR_PAGINA
from app.db import get_db
from app.routes.esquemas import PostOut, post_da_linha

# As rotas são "def" (síncronas): o FastAPI roda cada uma numa thread de um
# pool com 40 threads. Com 40 requisições lentas ao mesmo tempo, a 41ª espera.
router = APIRouter(tags=["feed"])

# As leituras, que são quase todo o tráfego do Mural, não passam mais pelo ORM.
# O SQL está escrito aqui, uma vez só: a cada requisição, o SQLAlchemy só
# preenche os parâmetros, sem montar a consulta de novo, e o resultado volta em
# linhas simples, sem criar um objeto Post e um Usuario para cada uma.
# As escritas continuam pelo ORM: são poucas, e nelas a conveniência compensa.

# A paginação é por cursor: a próxima página pede os posts mais antigos que o
# último que eu vi (antes_de = o criado_em dele). A primeira página não tem
# cursor: são os posts de antes do fim dos tempos.
SEM_CURSOR = datetime.max.replace(tzinfo=timezone.utc)

# A mesma consulta da etapa 04: os 20 mais recentes de cada pessoa que eu sigo
# (LATERAL) e, desses, os 20 mais novos de todos. Agora o autor e as curtidas
# vêm na mesma consulta: a página inteira sai de uma ida ao banco só.
# ⚠️ PROPOSITAL: as curtidas ainda são contadas na hora, curtida por curtida
FEED = text("""
    SELECT pagina.*,
           (SELECT count(*) FROM curtidas WHERE curtidas.post_id = pagina.id) AS curtidas
    FROM (
        SELECT recentes.id, recentes.texto, recentes.criado_em,
               usuarios.id AS autor_id, usuarios.nome AS autor_nome
        FROM seguidores
        CROSS JOIN LATERAL (
            SELECT * FROM posts
            WHERE posts.autor_id = seguidores.seguido_id AND posts.criado_em < :antes_de
            ORDER BY posts.criado_em DESC
            LIMIT :por_pagina
        ) AS recentes
        JOIN usuarios ON usuarios.id = recentes.autor_id
        WHERE seguidores.seguidor_id = :usuario_id
        ORDER BY recentes.criado_em DESC
        LIMIT :por_pagina
    ) AS pagina
    ORDER BY pagina.criado_em DESC
""")
# As curtidas são contadas fora da subconsulta "pagina": só para os 20 que
# ficaram, e não para todos os candidatos de cada pessoa seguida.

USUARIO = text("SELECT id, nome FROM usuarios WHERE id = :usuario_id")

POSTS_DO_PERFIL = text("""
    SELECT posts.id, posts.texto, posts.criado_em,
           (SELECT count(*) FROM curtidas WHERE curtidas.post_id = posts.id) AS curtidas
    FROM posts
    WHERE posts.autor_id = :usuario_id AND posts.criado_em < :antes_de
    ORDER BY posts.criado_em DESC
    LIMIT :por_pagina
""")


class PerfilOut(BaseModel):
    id: int
    nome: str
    posts: list[PostOut]


@router.get("/feed", response_model=list[PostOut])
def feed(usuario_id: int, antes_de: datetime | None = None, db: Session = Depends(get_db)):
    """Os posts de quem o usuário segue, dos mais novos para os mais antigos.

    A próxima página: antes_de = o criado_em do último post desta.
    """
    linhas = db.execute(FEED, {"usuario_id": usuario_id, "antes_de": antes_de or SEM_CURSOR, "por_pagina": POSTS_POR_PAGINA})
    return [post_da_linha(linha) for linha in linhas]


@router.get("/usuarios/{usuario_id}", response_model=PerfilOut)
def perfil(usuario_id: int, antes_de: datetime | None = None, db: Session = Depends(get_db)):
    """O perfil: o usuário e os posts dele, dos mais novos para os mais antigos."""
    usuario = db.execute(USUARIO, {"usuario_id": usuario_id}).first()
    if usuario is None:
        raise HTTPException(404, "Usuário não encontrado")
    # Todos os posts são do mesmo autor, que já foi lido acima
    parametros = {"usuario_id": usuario_id, "antes_de": antes_de or SEM_CURSOR, "por_pagina": POSTS_POR_PAGINA}
    autor = {"id": usuario.id, "nome": usuario.nome}
    posts = [post_da_linha(linha, autor) for linha in db.execute(POSTS_DO_PERFIL, parametros)]
    return {"id": usuario.id, "nome": usuario.nome, "posts": posts}

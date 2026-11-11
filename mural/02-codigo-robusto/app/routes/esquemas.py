from datetime import datetime

from pydantic import BaseModel, Field

from app.config import TAMANHO_MAXIMO_DO_TEXTO
from app.modelos import Post, Usuario


class AutorOut(BaseModel):
    id: int
    nome: str


class PostOut(BaseModel):
    id: int
    autor: AutorOut
    texto: str
    criado_em: datetime
    curtidas: int


class Escrever(BaseModel):
    # Sem login, para simplificar: quem escreve diz quem é
    usuario_id: int
    texto: str = Field(min_length=1, max_length=TAMANHO_MAXIMO_DO_TEXTO)


class Curtir(BaseModel):
    usuario_id: int


def post_out(post: Post, autor: Usuario) -> PostOut:
    # O autor já veio na mesma consulta do post (JOIN), e o total de curtidas é
    # uma coluna do post: montar a resposta não faz nenhuma consulta a mais
    return PostOut(id=post.id, autor=AutorOut(id=autor.id, nome=autor.nome), texto=post.texto, criado_em=post.criado_em, curtidas=post.curtidas)

"""
O formato de entrada e de saída da API, com msgspec no lugar do Pydantic.

Um msgspec.Struct é uma classe escrita em C: ler e gerar JSON com ela custa
uma fração do que custa no Pydantic. As respostas são as mesmas das outras
etapas. Este módulo não é compilado pelo mypyc: as Structs já são C.
"""

import msgspec


class ItemPedido(msgspec.Struct):
    assento: str
    tipo: str = "inteira"


class CriarPedido(msgspec.Struct):
    sessao_id: int
    nome: str
    cpf: str
    email: str
    cartao_token: str
    itens: list[ItemPedido]


class FilmeOut(msgspec.Struct):
    id: int
    titulo: str
    duracao_min: int
    classificacao: str
    sinopse: str


class SessaoOut(msgspec.Struct):
    id: int
    filme_id: int
    filme: str
    cinema: str
    sala: str
    inicio: str
    preco_inteira_centavos: int
    preco_meia_centavos: int


class Assento(msgspec.Struct):
    codigo: str
    status: str


class MapaOut(msgspec.Struct):
    sessao_id: int
    livres: int
    assentos: list[Assento]


class MapaDoCinema(msgspec.Struct):
    """O mapa como o sistema do cinema devolve: só os assentos."""

    assentos: list[Assento]


class IngressoOut(msgspec.Struct):
    codigo: str
    assento: str
    tipo: str
    preco_centavos: int
    qrcode_url: str


class PedidoOut(msgspec.Struct):
    id: int
    sessao_id: int
    nome: str
    email: str
    status: str
    subtotal_centavos: int
    taxa_centavos: int
    total_centavos: int
    criado_em: str
    ingressos: list[IngressoOut]


# Codificadores e decodificadores prontos: criar um a cada requisição custaria CPU
json_encoder = msgspec.json.Encoder()
pedido_decoder = msgspec.json.Decoder(CriarPedido)
mapa_do_cinema_decoder = msgspec.json.Decoder(MapaDoCinema)

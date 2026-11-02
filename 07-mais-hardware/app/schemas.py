from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.cpf import cpf_valido, normalizar


class FilmeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str
    duracao_min: int
    classificacao: str
    sinopse: str


class SessaoOut(BaseModel):
    id: int
    filme_id: int
    filme: str
    cinema: str
    sala: str
    inicio: datetime
    preco_inteira_centavos: int
    preco_meia_centavos: int


class AssentoOut(BaseModel):
    codigo: str
    status: str


class MapaDeAssentosOut(BaseModel):
    sessao_id: int
    livres: int
    assentos: list[AssentoOut]


class ResumoSessaoOut(BaseModel):
    sessao_id: int
    capacidade: int
    ingressos_vendidos: int
    meia_vendidas: int
    cota_meia: int
    maior_compra_por_cpf: int


class ItemPedido(BaseModel):
    assento: str = Field(min_length=2, max_length=4)
    tipo: Literal["inteira", "meia"] = "inteira"


class CriarPedido(BaseModel):
    sessao_id: int
    nome: str = Field(min_length=2)
    cpf: str
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+$")
    cartao_token: str
    itens: list[ItemPedido] = Field(min_length=1)

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, valor: str) -> str:
        cpf = normalizar(valor)
        if not cpf_valido(cpf):
            raise ValueError("CPF inválido")
        return cpf


class IngressoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    assento: str
    tipo: str
    preco_centavos: int

    @computed_field
    @property
    def qrcode_url(self) -> str:
        return f"/ingressos/{self.codigo}/qrcode"


class PedidoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sessao_id: int
    nome: str
    email: str
    status: str
    subtotal_centavos: int
    taxa_centavos: int
    total_centavos: int
    criado_em: datetime
    ingressos: list[IngressoOut]

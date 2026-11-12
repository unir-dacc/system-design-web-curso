"""
As exceções do Ingressa. Este módulo não é compilado pelo mypyc: na versão
1.18, uma exceção compilada que guarda atributos (self.pedido = ...) corrompe
a memória e derruba o processo.
"""

from typing import Any


class ErroHTTP(Exception):
    """Um erro que vira uma resposta com status e "detail", no mesmo formato das outras etapas."""

    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


class AssentosIndisponiveis(Exception):
    def __init__(self, assentos: list[str]) -> None:
        super().__init__("Assentos indisponíveis")
        self.assentos = assentos


class AssentosInexistentes(Exception):
    def __init__(self, assentos: list[str]) -> None:
        super().__init__("Assentos inexistentes")
        self.assentos = assentos


class PagamentoNaoRealizado(Exception):
    """O gateway falhou e confirmou que nada foi cobrado."""


class PagamentoNaoConcluido(Exception):
    """A compra parou no pagamento: nada foi cobrado e os assentos foram liberados."""

    def __init__(self, pedido: Any, status: int, detalhe: str) -> None:
        super().__init__(detalhe)
        self.pedido = pedido
        self.status = status
        self.detalhe = detalhe

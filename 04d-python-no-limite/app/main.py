"""
Ingressa com o Python no limite: o mesmo sistema da etapa 04 (cache, compra
dentro da requisição, sem fila e sem sala de espera), com tudo o que deixa o
Python mais rápido sem mudar a arquitetura:

- Granian: o servidor HTTP escrito em Rust, no lugar do uvicorn
- uvloop: o laço de eventos escrito em C, no lugar do asyncio padrão
- Sem framework: um roteador pequeno no lugar do FastAPI (app/rotas.py)
- msgspec no lugar do Pydantic, asyncpg e SQL à mão no lugar do SQLAlchemy
- aiohttp e Redis com hiredis: o HTTP e o protocolo do Redis lidos em C
- mypyc: os módulos do app compilados para C (veja o Dockerfile)

O Granian fala a interface RSGI: cada requisição chega como (scope, protocolo).
"""

import asyncio
import logging
import traceback
from typing import Any

from app import banco, clientes, rotas

log = logging.getLogger("ingressa")


class Ingressa:
    def __init__(self) -> None:
        self.pronto = False
        self.trava = asyncio.Lock()

    async def preparar(self) -> None:
        """Conecta e prepara o banco na primeira requisição (o healthcheck)."""
        async with self.trava:
            if not self.pronto:
                await banco.conectar()
                await clientes.conectar()
                await banco.preparar()
                self.pronto = True
                log.warning("Ingressa (Python no limite) pronto na porta 8000")

    async def __rsgi__(self, scope: Any, protocolo: Any) -> None:
        if not self.pronto:
            await self.preparar()
        try:
            status, corpo, tipo = await rotas.rotear(scope.method, scope.path, scope.query_string, protocolo)
        except Exception:
            traceback.print_exc()
            status, corpo, tipo = 500, b'{"detail":"Internal Server Error"}', rotas.JSON
        protocolo.response_bytes(status, [("content-type", tipo)], corpo)


app = Ingressa()

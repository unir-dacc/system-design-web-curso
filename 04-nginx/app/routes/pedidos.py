from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, compra
from app.db import get_db
from app.models import Pedido
from app.schemas import CriarPedido, PedidoOut

router = APIRouter(tags=["pedidos"])


# 202 = "aceito, ainda processando": o pagamento continua em segundo plano e o
# cliente acompanha o status em GET /pedidos/{id}
@router.post("/pedidos", status_code=202, response_model=PedidoOut)
async def criar_pedido(dados: CriarPedido, db: AsyncSession = Depends(get_db)):
    try:
        pedido = await compra.realizar_compra(db, dados)
    except compra.SessaoNaoEncontrada:
        raise HTTPException(404, "Sessão não encontrada")
    except (compra.RegraDeNegocio, clients.AssentosInexistentes) as erro:
        raise HTTPException(422, str(erro))
    except clients.AssentosIndisponiveis as erro:
        raise HTTPException(409, {"mensagem": "Assentos indisponíveis", "indisponiveis": erro.assentos})
    return PedidoOut.model_validate(pedido)


@router.get("/pedidos/{pedido_id}", response_model=PedidoOut)
async def detalhar_pedido(pedido_id: int, db: AsyncSession = Depends(get_db)):
    pedido = await db.get(Pedido, pedido_id)
    if pedido is None:
        raise HTTPException(404, "Pedido não encontrado")
    return PedidoOut.model_validate(pedido)

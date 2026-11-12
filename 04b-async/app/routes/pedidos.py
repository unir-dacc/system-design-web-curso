from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, compra
from app.db import get_db
from app.models import Pedido
from app.schemas import CriarPedido, PedidoOut

router = APIRouter(tags=["pedidos"])


@router.post("/pedidos", status_code=201, response_model=PedidoOut)
async def criar_pedido(dados: CriarPedido, db: AsyncSession = Depends(get_db)):
    try:
        pedido = await compra.realizar_compra(db, dados)
    except compra.SessaoNaoEncontrada:
        raise HTTPException(404, "Sessão não encontrada")
    except (compra.RegraDeNegocio, clients.AssentosInexistentes) as erro:
        raise HTTPException(422, str(erro))
    except clients.AssentosIndisponiveis as erro:
        raise HTTPException(409, {"mensagem": "Assentos indisponíveis", "indisponiveis": erro.assentos})
    except compra.PagamentoRecusado as erro:
        await erro.pedido.awaitable_attrs.ingressos
        return JSONResponse(
            status_code=402,
            content={"detail": "Pagamento recusado", "pedido": PedidoOut.model_validate(erro.pedido).model_dump(mode="json")},
        )
    except compra.FalhaNoPagamento as erro:
        await erro.pedido.awaitable_attrs.ingressos
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Não foi possível falar com o gateway de pagamento. Nada foi cobrado, tente de novo.",
                "pedido": PedidoOut.model_validate(erro.pedido).model_dump(mode="json"),
            },
        )
    return PedidoOut.model_validate(pedido)


@router.get("/pedidos/{pedido_id}", response_model=PedidoOut)
async def detalhar_pedido(pedido_id: int, db: AsyncSession = Depends(get_db)):
    pedido = await db.get(Pedido, pedido_id)
    if pedido is None:
        raise HTTPException(404, "Pedido não encontrado")
    await pedido.awaitable_attrs.ingressos
    return PedidoOut.model_validate(pedido)

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, compra, fila
from app.db import get_db
from app.models import Pedido
from app.schemas import CriarPedido, PedidoOut

router = APIRouter(tags=["pedidos"])


@router.post("/pedidos", status_code=201, response_model=PedidoOut)
async def criar_pedido(
    dados: CriarPedido,
    x_senha_fila: int | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    # Só compra quem passou pela fila e está dentro da janela de compra
    if x_senha_fila is None or not await fila.senha_valida(x_senha_fila):
        raise HTTPException(403, "Entre na fila virtual (POST /fila) e espere a sua vez")
    try:
        pedido = await compra.realizar_compra(db, dados)
    except compra.SessaoNaoEncontrada:
        await fila.depois_de_falhar(x_senha_fila)
        raise HTTPException(404, "Sessão não encontrada")
    except (compra.RegraDeNegocio, clients.AssentosInexistentes) as erro:
        await fila.depois_de_falhar(x_senha_fila)
        raise HTTPException(422, str(erro))
    except clients.AssentosIndisponiveis as erro:
        await fila.depois_de_falhar(x_senha_fila)
        raise HTTPException(409, {"mensagem": "Assentos indisponíveis", "indisponiveis": erro.assentos})
    except compra.PagamentoRecusado as erro:
        await fila.depois_de_falhar(x_senha_fila)
        return JSONResponse(
            status_code=402,
            content={"detail": "Pagamento recusado", "pedido": PedidoOut.model_validate(erro.pedido).model_dump(mode="json")},
        )
    await fila.usar(x_senha_fila)
    return PedidoOut.model_validate(pedido)


@router.get("/pedidos/{pedido_id}", response_model=PedidoOut)
async def detalhar_pedido(pedido_id: int, db: AsyncSession = Depends(get_db)):
    pedido = await db.get(Pedido, pedido_id)
    if pedido is None:
        raise HTTPException(404, "Pedido não encontrado")
    return PedidoOut.model_validate(pedido)

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import clients, compra
from app.db import get_db
from app.models import Pedido
from app.routes.sala import exige_passe
from app.schemas import CriarPedido, PedidoOut

router = APIRouter(tags=["pedidos"])


# 202 = "aceito, ainda processando": os assentos estão reservados e o worker
# conclui a compra. O cliente não precisa esperar: o resultado chega por e-mail
# (e, se ele quiser conferir, em GET /pedidos/{id}).
@router.post("/pedidos", status_code=202, response_model=PedidoOut, dependencies=[Depends(exige_passe)])
def criar_pedido(dados: CriarPedido, response: Response, db: Session = Depends(get_db)):
    try:
        pedido = compra.realizar_compra(db, dados)
    except compra.SessaoNaoEncontrada:
        raise HTTPException(404, "Sessão não encontrada")
    except (compra.RegraDeNegocio, clients.AssentosInexistentes) as erro:
        raise HTTPException(422, str(erro))
    except clients.AssentosIndisponiveis as erro:
        raise HTTPException(409, {"mensagem": "Assentos indisponíveis", "indisponiveis": erro.assentos})
    response.headers["Location"] = f"/pedidos/{pedido.id}"
    return PedidoOut.model_validate(pedido)


@router.get("/pedidos/{pedido_id}", response_model=PedidoOut)
def detalhar_pedido(pedido_id: int, db: Session = Depends(get_db)):
    pedido = db.get(Pedido, pedido_id)
    if pedido is None:
        raise HTTPException(404, "Pedido não encontrado")
    return PedidoOut.model_validate(pedido)

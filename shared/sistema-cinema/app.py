"""
Sistema de Assentos do Cinema (SIMULADO)

Representa o sistema legado da rede de cinemas. É ele quem manda nos
assentos: o Ingressa precisa consultá-lo para mostrar o mapa da sala,
reservar assentos e confirmar a venda.

Comportamento proposital:
- é LENTO: cada operação tem latência configurável
- aguenta POUCAS requisições simultâneas (max_concorrencia). O excedente
  espera numa fila, então quanto mais carga, maior a latência
- é CORRETO: a reserva é atômica, nunca vende o mesmo assento duas vezes
- reservas não confirmadas expiram depois de reserva_ttl_s

Tudo fica em memória: reiniciar o container zera o estado.
"""

import asyncio
import json
import os
import random
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

SEED_PATH = os.getenv("SEED_PATH", "/seed/catalogo.json")


class Config(BaseModel):
    latencia_mapa_ms: int = int(os.getenv("LATENCIA_MAPA_MS", "800"))
    latencia_reserva_ms: int = int(os.getenv("LATENCIA_RESERVA_MS", "600"))
    latencia_confirmacao_ms: int = int(os.getenv("LATENCIA_CONFIRMACAO_MS", "400"))
    variacao_pct: int = int(os.getenv("VARIACAO_PCT", "30"))
    max_concorrencia: int = int(os.getenv("MAX_CONCORRENCIA", "10"))
    taxa_erro: float = float(os.getenv("TAXA_ERRO", "0"))
    reserva_ttl_s: int = int(os.getenv("RESERVA_TTL_S", "600"))


class ConfigParcial(BaseModel):
    latencia_mapa_ms: int | None = None
    latencia_reserva_ms: int | None = None
    latencia_confirmacao_ms: int | None = None
    variacao_pct: int | None = None
    max_concorrencia: int | None = Field(default=None, ge=1)
    taxa_erro: float | None = Field(default=None, ge=0, le=1)
    reserva_ttl_s: int | None = None


class PedidoReserva(BaseModel):
    assentos: list[str] = Field(min_length=1)


config = Config()
semaforo = asyncio.Semaphore(config.max_concorrencia)
metricas = {"na_fila": 0, "em_atendimento": 0, "atendidas": 0}

# sessao_id -> codigo do assento -> {"status": livre|reservado|vendido, "reserva_id": str|None}
assentos: dict[int, dict[str, dict]] = {}
# reserva_id -> {"sessao_id", "assentos", "expira_em", "status": pendente|confirmada|cancelada|expirada}
reservas: dict[str, dict] = {}


def carregar_estado() -> None:
    with open(SEED_PATH) as f:
        catalogo = json.load(f)
    salas = {s["id"]: s for s in catalogo["salas"]}
    assentos.clear()
    reservas.clear()
    for sessao in catalogo["sessoes"]:
        sala = salas[sessao["sala_id"]]
        assentos[sessao["id"]] = {
            f"{fileira}{numero}": {"status": "livre", "reserva_id": None}
            for fileira in sala["fileiras"]
            for numero in range(1, sala["assentos_por_fileira"] + 1)
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    carregar_estado()
    yield


app = FastAPI(title="Sistema de Assentos do Cinema (simulado)", lifespan=lifespan)


def com_variacao(latencia_ms: int) -> float:
    variacao = latencia_ms * config.variacao_pct / 100
    return max(0.0, random.uniform(latencia_ms - variacao, latencia_ms + variacao)) / 1000


@asynccontextmanager
async def sistema_legado(latencia_ms: int):
    """Simula o atendimento do sistema legado: fila, latência e erros."""
    metricas["na_fila"] += 1
    async with semaforo:
        metricas["na_fila"] -= 1
        metricas["em_atendimento"] += 1
        try:
            await asyncio.sleep(com_variacao(latencia_ms))
            if random.random() < config.taxa_erro:
                raise HTTPException(503, "Sistema do cinema indisponível")
            yield
        finally:
            metricas["em_atendimento"] -= 1
            metricas["atendidas"] += 1


def mapa_da_sessao(sessao_id: int) -> dict[str, dict]:
    if sessao_id not in assentos:
        raise HTTPException(404, "Sessão não encontrada")
    expirar_reservas(sessao_id)
    return assentos[sessao_id]


def expirar_reservas(sessao_id: int) -> None:
    agora = time.time()
    for reserva_id, reserva in reservas.items():
        if reserva["sessao_id"] == sessao_id and reserva["status"] == "pendente" and reserva["expira_em"] < agora:
            liberar(reserva_id, novo_status="expirada")


def liberar(reserva_id: str, novo_status: str) -> None:
    reserva = reservas[reserva_id]
    for codigo in reserva["assentos"]:
        assento = assentos[reserva["sessao_id"]][codigo]
        if assento["reserva_id"] == reserva_id:
            assento.update(status="livre", reserva_id=None)
    reserva["status"] = novo_status


def buscar_reserva(reserva_id: str) -> dict:
    reserva = reservas.get(reserva_id)
    if reserva is None:
        raise HTTPException(404, "Reserva não encontrada")
    expirar_reservas(reserva["sessao_id"])
    return reserva


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/sessoes/{sessao_id}/assentos")
async def mapa_de_assentos(sessao_id: int):
    async with sistema_legado(config.latencia_mapa_ms):
        mapa = mapa_da_sessao(sessao_id)
        return {
            "sessao_id": sessao_id,
            "assentos": [{"codigo": codigo, "status": a["status"]} for codigo, a in mapa.items()],
        }


@app.post("/sessoes/{sessao_id}/reservas", status_code=201)
async def reservar(sessao_id: int, pedido: PedidoReserva):
    async with sistema_legado(config.latencia_reserva_ms):
        mapa = mapa_da_sessao(sessao_id)
        codigos = [c.upper() for c in pedido.assentos]

        inexistentes = [c for c in codigos if c not in mapa]
        if inexistentes:
            raise HTTPException(422, {"mensagem": "Assentos inexistentes", "assentos": inexistentes})

        # Não existe nenhum "await" entre verificar e marcar os assentos, então
        # nenhuma outra requisição consegue rodar no meio: a reserva é atômica.
        indisponiveis = [c for c in codigos if mapa[c]["status"] != "livre"]
        if indisponiveis:
            raise HTTPException(409, {"mensagem": "Assentos indisponíveis", "indisponiveis": indisponiveis})

        reserva_id = uuid.uuid4().hex
        for c in codigos:
            mapa[c].update(status="reservado", reserva_id=reserva_id)
        reservas[reserva_id] = {
            "sessao_id": sessao_id,
            "assentos": codigos,
            "expira_em": time.time() + config.reserva_ttl_s,
            "status": "pendente",
        }
        return {"reserva_id": reserva_id, **reservas[reserva_id]}


@app.post("/reservas/{reserva_id}/confirmar")
async def confirmar(reserva_id: str):
    async with sistema_legado(config.latencia_confirmacao_ms):
        reserva = buscar_reserva(reserva_id)
        if reserva["status"] in ("expirada", "cancelada"):
            raise HTTPException(410, f"Reserva {reserva['status']}")
        if reserva["status"] == "pendente":
            for c in reserva["assentos"]:
                assentos[reserva["sessao_id"]][c]["status"] = "vendido"
            reserva["status"] = "confirmada"
        return {"reserva_id": reserva_id, **reserva}


@app.delete("/reservas/{reserva_id}", status_code=204)
async def cancelar(reserva_id: str):
    async with sistema_legado(config.latencia_confirmacao_ms):
        reserva = buscar_reserva(reserva_id)
        if reserva["status"] == "pendente":
            liberar(reserva_id, novo_status="cancelada")
        return Response(status_code=204)


# --- Administração (usada nas demos para mudar o comportamento ao vivo) ---


@app.get("/admin/config")
async def ver_config():
    return config


@app.patch("/admin/config")
async def alterar_config(parcial: ConfigParcial):
    global semaforo
    mudancas = parcial.model_dump(exclude_none=True)
    for campo, valor in mudancas.items():
        setattr(config, campo, valor)
    if "max_concorrencia" in mudancas:
        semaforo = asyncio.Semaphore(config.max_concorrencia)
    return config


@app.get("/admin/estado")
async def estado():
    resumo = {}
    for sessao_id in assentos:
        mapa = mapa_da_sessao(sessao_id)
        contagem = {"livre": 0, "reservado": 0, "vendido": 0}
        for a in mapa.values():
            contagem[a["status"]] += 1
        resumo[sessao_id] = contagem
    return {"fila": metricas, "sessoes": resumo}


@app.post("/admin/reset")
async def reset():
    carregar_estado()
    metricas["atendidas"] = 0
    return {"status": "estado reiniciado"}

"""
Gateway de Pagamento (SIMULADO)

Representa um provedor de pagamento externo. Diferente do sistema do cinema,
ele aguenta muita carga, mas cada cobrança DEMORA (análise antifraude,
comunicação com a bandeira do cartão...).

Comportamento configurável ao vivo via /admin/config:
- latencia_ms       quanto tempo cada cobrança leva
- taxa_recusa       fração de cartões recusados (aleatório)
- taxa_erro         fração de respostas 500 (o gateway "engasga")
- taxa_travamento   fração de requisições que NUNCA respondem

Cartões de teste:
- tok_aprovado      sempre aprova
- tok_recusado      sempre recusa
- qualquer outro    aprova ou recusa conforme taxa_recusa

Suporta o header Idempotency-Key: repetir a mesma chave devolve a mesma
cobrança em vez de cobrar de novo.
"""

import asyncio
import os
import random
import time
import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Gateway de Pagamento (simulado)")


class Config(BaseModel):
    latencia_ms: int = int(os.getenv("LATENCIA_MS", "3000"))
    variacao_pct: int = int(os.getenv("VARIACAO_PCT", "30"))
    taxa_recusa: float = float(os.getenv("TAXA_RECUSA", "0.05"))
    taxa_erro: float = float(os.getenv("TAXA_ERRO", "0"))
    taxa_travamento: float = float(os.getenv("TAXA_TRAVAMENTO", "0"))


class ConfigParcial(BaseModel):
    latencia_ms: int | None = None
    variacao_pct: int | None = None
    taxa_recusa: float | None = Field(default=None, ge=0, le=1)
    taxa_erro: float | None = Field(default=None, ge=0, le=1)
    taxa_travamento: float | None = Field(default=None, ge=0, le=1)


class NovaCobranca(BaseModel):
    valor_centavos: int = Field(gt=0)
    cartao_token: str
    referencia: str | None = None


config = Config()
cobrancas: dict[str, dict] = {}
por_chave_idempotencia: dict[str, str] = {}


def com_variacao(latencia_ms: int) -> float:
    variacao = latencia_ms * config.variacao_pct / 100
    return max(0.0, random.uniform(latencia_ms - variacao, latencia_ms + variacao)) / 1000


def decidir_status(cartao_token: str) -> str:
    if cartao_token == "tok_aprovado":
        return "aprovada"
    if cartao_token == "tok_recusado":
        return "recusada"
    return "recusada" if random.random() < config.taxa_recusa else "aprovada"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/cobrancas", status_code=201)
async def cobrar(nova: NovaCobranca, idempotency_key: str | None = Header(default=None)):
    if idempotency_key and idempotency_key in por_chave_idempotencia:
        return cobrancas[por_chave_idempotencia[idempotency_key]]

    if random.random() < config.taxa_travamento:
        await asyncio.sleep(3600)
        raise HTTPException(504, "Cobrança travada, nada foi cobrado")

    await asyncio.sleep(com_variacao(config.latencia_ms))

    if random.random() < config.taxa_erro:
        raise HTTPException(500, "Erro interno no gateway")

    cobranca = {
        "id": f"cob_{uuid.uuid4().hex[:16]}",
        "status": decidir_status(nova.cartao_token),
        "valor_centavos": nova.valor_centavos,
        "referencia": nova.referencia,
        "criada_em": time.time(),
    }
    cobrancas[cobranca["id"]] = cobranca
    if idempotency_key:
        por_chave_idempotencia[idempotency_key] = cobranca["id"]
    return cobranca


@app.get("/cobrancas")
async def listar(referencia: str | None = None):
    return [c for c in cobrancas.values() if referencia is None or c["referencia"] == referencia]


@app.get("/cobrancas/{cobranca_id}")
async def detalhar(cobranca_id: str):
    if cobranca_id not in cobrancas:
        raise HTTPException(404, "Cobrança não encontrada")
    return cobrancas[cobranca_id]


# --- Administração (usada nas demos para mudar o comportamento ao vivo) ---


@app.get("/admin/config")
async def ver_config():
    return config


@app.patch("/admin/config")
async def alterar_config(parcial: ConfigParcial):
    for campo, valor in parcial.model_dump(exclude_none=True).items():
        setattr(config, campo, valor)
    return config


@app.get("/admin/estatisticas")
async def estatisticas():
    aprovadas = [c for c in cobrancas.values() if c["status"] == "aprovada"]
    return {
        "total": len(cobrancas),
        "aprovadas": len(aprovadas),
        "recusadas": len(cobrancas) - len(aprovadas),
        "valor_aprovado_centavos": sum(c["valor_centavos"] for c in aprovadas),
    }


@app.post("/admin/reset")
async def reset():
    cobrancas.clear()
    por_chave_idempotencia.clear()
    return {"status": "estado reiniciado"}

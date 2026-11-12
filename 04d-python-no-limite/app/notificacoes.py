import io
from email.message import EmailMessage
from typing import Any

import aiosmtplib
import qrcode

from app.config import FUSO_HORARIO, SMTP_HOST, SMTP_PORT

REMETENTE = "ingressos@ingressa.local"


def gerar_qrcode_png(codigo: str) -> bytes:
    # Gerar imagem é trabalho de CPU, não de I/O. A mesma biblioteca das outras
    # etapas: comparada com as alternativas, foi a que gastou menos CPU.
    imagem: Any = qrcode.make(f"INGRESSA:{codigo}", box_size=10, border=2)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


async def enviar_confirmacao(pedido: Any, sessao: Any, ingressos: list[tuple[str, str, str, int]]) -> None:
    """Manda o e-mail com os QR codes. `ingressos`: (código, assento, tipo, preço) de cada um."""
    linhas = [
        f"Olá, {pedido.nome}!",
        "",
        f"Seu pedido #{pedido.id} está confirmado.",
        f"{sessao.filme} - {sessao.cinema}, {sessao.sala}",
        f"Início: {sessao.inicio.astimezone(FUSO_HORARIO):%d/%m/%Y %H:%M}",
        "",
    ]
    linhas += [f"- Assento {assento} ({tipo}): R$ {preco / 100:.2f}" for _, assento, tipo, preco in ingressos]
    linhas += [
        "",
        f"Taxa de conveniência: R$ {pedido.taxa_centavos / 100:.2f}",
        f"Total: R$ {pedido.total_centavos / 100:.2f}",
    ]

    mensagem = EmailMessage()
    mensagem["From"] = REMETENTE
    mensagem["To"] = pedido.email
    mensagem["Subject"] = f"Seus ingressos para {sessao.filme}"
    mensagem.set_content("\n".join(linhas))
    for codigo, assento, _, _ in ingressos:
        mensagem.add_attachment(gerar_qrcode_png(codigo), maintype="image", subtype="png", filename=f"ingresso-{assento}.png")

    # O SMTP assíncrono: a espera pelo servidor de e-mail não prende o laço de eventos
    await aiosmtplib.send(mensagem, hostname=SMTP_HOST, port=SMTP_PORT)

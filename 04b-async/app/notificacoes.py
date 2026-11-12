import asyncio
import io
import smtplib
from email.message import EmailMessage

import qrcode

from app.config import FUSO_HORARIO, SMTP_HOST, SMTP_PORT
from app.models import Pedido, Sessao


def gerar_qrcode_png(codigo: str) -> bytes:
    # Gerar imagem é trabalho de CPU, não de I/O.
    imagem = qrcode.make(f"INGRESSA:{codigo}", box_size=10, border=2)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


async def enviar_confirmacao(pedido: Pedido, sessao: Sessao) -> None:
    # No async, as relações são carregadas antes, com await
    sala = await sessao.awaitable_attrs.sala
    await sessao.awaitable_attrs.filme
    await sala.awaitable_attrs.cinema
    await pedido.awaitable_attrs.ingressos
    # Gerar os QR codes (CPU) e falar com o SMTP (biblioteca síncrona) ficam
    # numa thread: no laço de eventos, travariam todas as outras requisições
    await asyncio.to_thread(_enviar_confirmacao, pedido, sessao)


def _enviar_confirmacao(pedido: Pedido, sessao: Sessao) -> None:
    linhas = [
        f"Olá, {pedido.nome}!",
        "",
        f"Seu pedido #{pedido.id} está confirmado.",
        f"{sessao.filme.titulo} - {sessao.sala.cinema.nome}, {sessao.sala.nome}",
        f"Início: {sessao.inicio.astimezone(FUSO_HORARIO):%d/%m/%Y %H:%M}",
        "",
    ]
    linhas += [f"- Assento {i.assento} ({i.tipo}): R$ {i.preco_centavos / 100:.2f}" for i in pedido.ingressos]
    linhas += ["", f"Taxa de conveniência: R$ {pedido.taxa_centavos / 100:.2f}", f"Total: R$ {pedido.total_centavos / 100:.2f}"]

    mensagem = EmailMessage()
    mensagem["Subject"] = f"Seus ingressos para {sessao.filme.titulo}"
    mensagem["From"] = "ingressos@ingressa.local"
    mensagem["To"] = pedido.email
    mensagem.set_content("\n".join(linhas))
    for ingresso in pedido.ingressos:
        mensagem.add_attachment(
            gerar_qrcode_png(ingresso.codigo),
            maintype="image",
            subtype="png",
            filename=f"ingresso-{ingresso.assento}.png",
        )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.send_message(mensagem)

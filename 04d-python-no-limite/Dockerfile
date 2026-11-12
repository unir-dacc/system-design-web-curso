# 1. Compilação: instala as dependências e compila os módulos do app com o
# mypyc, que transforma o código Python (com as anotações de tipo) em C.
FROM python:3.14 AS compilacao
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
RUN python -m venv /venv
ENV PATH=/venv/bin:$PATH
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt mypy==1.18.2 setuptools
COPY app ./app
# Ficam de fora: modelos.py (as Structs do msgspec já são C), erros.py (o
# motivo está nele) e main.py (a porta de entrada do Granian, que só repassa
# a requisição)
RUN mypyc --ignore-missing-imports app/config.py app/cpf.py app/banco.py app/cache.py \
      app/clientes.py app/notificacoes.py app/compra.py app/rotas.py \
 && pip uninstall -y mypy setuptools

# 2. A imagem que roda: só o Python, as dependências e o app compilado
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/venv/bin:$PATH
WORKDIR /srv
COPY --from=compilacao /venv /venv
COPY --from=compilacao /srv /srv
EXPOSE 8000
HEALTHCHECK --interval=2s --timeout=2s --retries=30 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
# Um único processo, como nas outras etapas: o Granian (em Rust) lê o HTTP e
# o uvloop (em C) roda o laço de eventos
CMD ["granian", "--interface", "rsgi", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--loop", "uvloop", "app.main:app"]

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
# Na primeira subida, criar a rede inicial leva alguns minutos: durante o
# start-period, as falhas do teste de saúde não contam
HEALTHCHECK --start-period=600s --interval=2s --timeout=2s --retries=30 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
# 4 processos por réplica (o lado do app não tem limite de CPU)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

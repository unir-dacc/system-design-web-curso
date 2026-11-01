FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
HEALTHCHECK --interval=2s --timeout=2s --retries=30 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
# Um único processo. Veremos por que isso é um problema na aula 02.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

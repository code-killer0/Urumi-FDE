FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8003

RUN groupadd -g 1000 mcpuser && \
    useradd -u 1000 -g mcpuser -s /bin/sh -m mcpuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
RUN chown -R 1000:1000 /app

USER 1000:1000

EXPOSE 8003

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/healthz')" || exit 1

CMD ["python", "server.py"]

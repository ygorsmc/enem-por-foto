FROM python:3.12-slim

# Redis embutido no mesmo contêiner (economia: 1 único Container App no
# Azure). Só ouve em 127.0.0.1 — nunca exposto fora do contêiner.
RUN apt-get update && apt-get install -y --no-install-recommends redis-server \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# AOF do Redis: consentimento LGPD (sem TTL) sobrevive a restart do contêiner.
VOLUME /data

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]

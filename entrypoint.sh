#!/bin/sh
# Sobe o Redis embutido (AOF em /data, só localhost) e espera ele responder
# antes de subir a app — evita a corrida de a app conectar antes do Redis
# terminar o fork do --daemonize.
#
# Só quando REDIS_URL aponta pra localhost: no deploy scale-to-zero (Azure
# Container Apps, minReplicas=0) o estado vive num Redis EXTERNO (Upstash),
# porque o Redis embutido morre junto com o contêiner quando a réplica dorme.
# Nesse caso pular o redis-server (ver deploy/README.md).
set -e

REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"

case "$REDIS_URL" in
    *127.0.0.1*|*localhost*)
        redis-server --daemonize yes --appendonly yes --dir /data --bind 127.0.0.1 --port 6379
        until redis-cli -h 127.0.0.1 ping >/dev/null 2>&1; do
            sleep 0.1
        done
        ;;
    *)
        echo "REDIS_URL is external — skipping embedded redis-server"
        ;;
esac

exec uvicorn src.main:app --host 0.0.0.0 --port 8000

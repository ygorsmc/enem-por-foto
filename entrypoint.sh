#!/bin/sh
# Sobe o Redis embutido (AOF em /data, só localhost) e espera ele responder
# antes de subir a app — evita a corrida de a app conectar antes do Redis
# terminar o fork do --daemonize.
set -e

redis-server --daemonize yes --appendonly yes --dir /data --bind 127.0.0.1 --port 6379

until redis-cli -h 127.0.0.1 ping >/dev/null 2>&1; do
    sleep 0.1
done

exec uvicorn src.main:app --host 0.0.0.0 --port 8000

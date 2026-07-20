#!/usr/bin/env bash
# Deploy scale-to-zero do Corretor ENEM no Azure, num comando só.
#
# Faz: resource group → ACR + build da imagem NA NUVEM (não precisa de Docker
# local) → deployment do main.bicep → setWebhook do Telegram. Idempotente:
# rodar de novo atualiza o que mudou.
#
# Pré-requisitos:
#   - az CLI logado (`az login`) na assinatura de estudante.
#   - Redis externo já criado (Upstash free tier) — a URL vai em REDIS_URL.
#   - deploy/.env.deploy preenchido (copie de deploy/.env.deploy.example).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env.deploy ]; then
    echo "ERRO: crie deploy/.env.deploy a partir de deploy/.env.deploy.example" >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
# 1) Segredos compartilhados do app (.env da raiz, se existir).
[ -f ../.env ] && . ../.env
# 2) Config de deploy — precedência sobre o .env (pode sobrescrever REDIS_URL etc.).
. ./.env.deploy
set +a

: "${RESOURCE_GROUP:?defina no .env.deploy}"
: "${LOCATION:?defina no .env.deploy}"
: "${ACR_NAME:?defina no .env.deploy}"
: "${REDIS_URL:?defina no .env.deploy (Upstash)}"
: "${TELEGRAM_BOT_TOKEN:?defina no .env.deploy}"
: "${MISTRAL_API_KEY:?defina no .env.deploy}"

APP_NAME="${APP_NAME:-enem-reviewer}"
IMAGE_TAG="${IMAGE_TAG:-enem-reviewer:latest}"

echo "==> [1/4] Resource group: $RESOURCE_GROUP ($LOCATION)"
az group create -n "$RESOURCE_GROUP" -l "$LOCATION" -o none

echo "==> [2/4] ACR + build da imagem na nuvem (contexto = raiz do repo)"
az acr create -n "$ACR_NAME" -g "$RESOURCE_GROUP" --sku Basic --admin-enabled true -o none 2>/dev/null || true
az acr build -r "$ACR_NAME" -t "$IMAGE_TAG" .. -o none
REGISTRY_SERVER=$(az acr show -n "$ACR_NAME" -g "$RESOURCE_GROUP" --query loginServer -o tsv)
REGISTRY_USERNAME=$(az acr credential show -n "$ACR_NAME" -g "$RESOURCE_GROUP" --query username -o tsv)
REGISTRY_PASSWORD=$(az acr credential show -n "$ACR_NAME" -g "$RESOURCE_GROUP" --query 'passwords[0].value' -o tsv)
IMAGE="$REGISTRY_SERVER/$IMAGE_TAG"

echo "==> [3/4] Deployment do Bicep"
FQDN=$(az deployment group create \
    -g "$RESOURCE_GROUP" \
    --template-file main.bicep \
    --query properties.outputs.fqdn.value -o tsv \
    --parameters \
        appName="$APP_NAME" \
        containerImage="$IMAGE" \
        registryServer="$REGISTRY_SERVER" \
        registryUsername="$REGISTRY_USERNAME" \
        registryPassword="$REGISTRY_PASSWORD" \
        redisUrl="$REDIS_URL" \
        telegramBotToken="$TELEGRAM_BOT_TOKEN" \
        telegramWebhookSecret="${TELEGRAM_WEBHOOK_SECRET:-}" \
        mistralApiKey="$MISTRAL_API_KEY" \
        correctionProvider="${CORRECTION_PROVIDER:-deepseek}" \
        correctionModel="${CORRECTION_MODEL:-deepseek-v4-flash}" \
        correctionEffort="${CORRECTION_EFFORT:-max}" \
        deepseekApiKey="${DEEPSEEK_API_KEY:-}" \
        googleApiKey="${GOOGLE_API_KEY:-}" \
        anthropicApiKey="${ANTHROPIC_API_KEY:-}" \
        openaiApiKey="${OPENAI_API_KEY:-}" \
        maritacaApiKey="${MARITACA_API_KEY:-}")

echo "==> [4/4] setWebhook do Telegram → https://$FQDN/v1/webhook/telegram"
RESP=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
    --data-urlencode "url=https://$FQDN/v1/webhook/telegram" \
    ${TELEGRAM_WEBHOOK_SECRET:+--data-urlencode "secret_token=${TELEGRAM_WEBHOOK_SECRET}"})
echo "    Telegram: $RESP"

echo ""
echo "✅ Pronto. App: https://$FQDN"
echo "   Logs:  az containerapp logs show -n $APP_NAME -g $RESOURCE_GROUP --follow"

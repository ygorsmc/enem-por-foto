#!/usr/bin/env bash
# Deploy scale-to-zero do Corretor ENEM no Azure, num comando só.
#
# Faz: resource group → build da imagem (Docker local) → push para o GitHub
# Container Registry (ghcr.io, pacote PÚBLICO = gratuito) → deployment do
# main.bicep → (modo híbrido) envio dos artefatos do modelo para um contêiner
# PRIVADO do Blob → setWebhook do Telegram. Idempotente: rodar de novo atualiza o
# que mudou (cada deploy gera uma tag nova, então o Container App sempre sobe
# uma revisão com a imagem nova).
#
# Por que GHCR e não ACR: o Azure Container Registry Basic cobra uma diária
# fixa (~US$ 5/mês) mesmo parado; o GHCR é grátis para pacote público. A
# imagem não leva segredo nenhum (o .dockerignore exclui .env, _local/ etc.;
# os segredos entram como secrets do Container App) e o código já é público.
# Também não leva o modelo do modo híbrido (artefatos fora da imagem, conferido
# depois do build): ele vai para o Blob privado e o app baixa por link SAS.
#
# Pré-requisitos:
#   - az CLI logado (`az login`) na assinatura de estudante.
#   - Docker local rodando.
#   - Login no ghcr.io com um token que tenha o escopo write:packages (uma vez):
#       gh auth refresh -h github.com -s write:packages
#       gh auth token | docker login ghcr.io -u <dono> --password-stdin
#   - Redis externo já criado (Upstash free tier) — a URL vai em REDIS_URL.
#   - deploy/.env.deploy preenchido (copie de deploy/.env.deploy.example).
#   - Na 1ª publicação, deixar o pacote público no GitHub (o script confere e
#     para com as instruções se ainda estiver privado).
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
: "${REDIS_URL:?defina no .env.deploy (Upstash)}"
: "${TELEGRAM_BOT_TOKEN:?defina no .env.deploy}"
: "${MISTRAL_API_KEY:?defina no .env.deploy}"

# O app fala o protocolo Redis (redis-py). O Upstash também mostra um endereço
# https:// da API REST, que o app NÃO usa: com ele o app sobe e só quebra na 1ª
# mensagem do aluno.
case "$REDIS_URL" in
    redis://*.upstash.io* | redis://*@*.upstash.io*)
        echo "ERRO: o Upstash só aceita conexão com TLS — troque redis:// por rediss:// no REDIS_URL." >&2
        exit 1
        ;;
    redis://* | rediss://*) ;;
    *)
        echo "ERRO: o REDIS_URL precisa começar com rediss:// (no Upstash: aba de conexão Redis/TCP," >&2
        echo "      formato rediss://default:SENHA@HOST.upstash.io:6379). O https:// é o da API REST." >&2
        exit 1
        ;;
esac

# Redis apagado (ex.: banco do Upstash removido) só quebraria na 1ª mensagem do
# aluno: confere o DNS antes. Só o host vai para a tela, nunca a senha da URL.
REDIS_HOST=$(echo "$REDIS_URL" | sed -E 's#^[a-z]+://([^@/]*@)?([^:/]+).*#\2#')
if ! python3 -c "import socket, sys; socket.getaddrinfo(sys.argv[1], None)" "$REDIS_HOST" 2>/dev/null; then
    echo "ERRO: o host do REDIS_URL ($REDIS_HOST) não resolve no DNS — o banco foi apagado?" >&2
    echo "      Crie um novo no Upstash (free tier) e atualize o REDIS_URL." >&2
    exit 1
fi

# Modo híbrido: chave do Jev e artefatos do modelo (gerados no laboratório, fora do git).
CORRECTION_MODE="${CORRECTION_MODE:-llm}"
ARTIFACTS_DIR=../src/correction/hybrid/artifacts
if [ "$CORRECTION_MODE" = "hibrido" ]; then
    : "${JEV_API_KEY:?CORRECTION_MODE=hibrido exige JEV_API_KEY no .env}"
    for f in model.joblib questions.json checklist.json meta.json; do
        if [ ! -f "$ARTIFACTS_DIR/$f" ]; then
            echo "ERRO: CORRECTION_MODE=hibrido, mas falta $ARTIFACTS_DIR/$f" >&2
            echo "      (gere com _local/scripts/jev_v4_export.py ou use CORRECTION_MODE=llm)" >&2
            exit 1
        fi
    done
fi

APP_NAME="${APP_NAME:-enem-reviewer}"

# Container Apps Environment. Precisa ser do tipo padrão: o modo "Express" não
# aceita regras de escala customizadas (KEDA), e a regra azure-queue do main.bicep
# é o que mantém a réplica viva enquanto há redação na fila.
#   - resource ID fixado no .env.deploy → conferido aqui (um ID já apagado ou de um
#     Environment Express só falharia no meio do Bicep);
#   - em branco → tenta descobrir um Environment padrão já existente em $LOCATION e
#     reaproveitá-lo; se não achar, segue vazio e o Bicep cria um novo.
if [ -n "${EXISTING_ENV_ID:-}" ]; then
    if ! ENV_MODE=$(az containerapp env show --ids "$EXISTING_ENV_ID" --query "properties.environmentMode" -o tsv 2>/dev/null); then
        echo "ERRO: o EXISTING_ENV_ID aponta para um Environment que não existe: ${EXISTING_ENV_ID##*/}" >&2
        echo "      Corrija o resource ID ou deixe em branco para o deploy.sh procurar um em $LOCATION." >&2
        exit 1
    fi
    if [ "$ENV_MODE" = "Express" ]; then
        echo "ERRO: o EXISTING_ENV_ID aponta para um Environment Express (${EXISTING_ENV_ID##*/}), que não aceita" >&2
        echo "      a regra de escala da fila. Use um Environment padrão ou deixe em branco." >&2
        exit 1
    fi
else
    # location vem como "Brazil South" (display name); normaliza pra comparar
    # com o canônico "brazilsouth" do .env.deploy.
    norm_target=$(echo "$LOCATION" | tr -d ' ' | tr '[:upper:]' '[:lower:]')
    EXISTING_ENV_ID=$(az containerapp env list \
        --query "[].{id:id, location:location, mode:properties.environmentMode}" -o tsv 2>/dev/null \
        | while IFS=$'\t' read -r id loc mode; do
            norm_loc=$(echo "$loc" | tr -d ' ' | tr '[:upper:]' '[:lower:]')
            [ "$norm_loc" = "$norm_target" ] && [ "$mode" != "Express" ] && echo "$id" && break
          done || true)
    if [ -n "$EXISTING_ENV_ID" ]; then
        echo "==> Reaproveitando Container Apps Environment existente em $LOCATION"
    else
        echo "==> Nenhum Container Apps Environment padrão em $LOCATION: o Bicep cria um ($APP_NAME-env)"
    fi
fi

# ── Imagem no GHCR ───────────────────────────────────────────────────────────
# Dono = GHCR_OWNER do .env.deploy ou, em branco, o dono do `git remote origin`.
REPO_URL=$(git -C .. remote get-url origin 2>/dev/null || true)
GHCR_OWNER="${GHCR_OWNER:-$(echo "$REPO_URL" | sed -nE 's#.*github\.com[:/]([^/]+)/.*#\1#p')}"
: "${GHCR_OWNER:?defina GHCR_OWNER no .env.deploy (seu usuário do GitHub)}"
GHCR_OWNER=$(echo "$GHCR_OWNER" | tr '[:upper:]' '[:lower:]') # o ghcr.io só aceita minúsculas
IMAGE_NAME="${IMAGE_NAME:-enem-reviewer}"
IMAGE_REPO="ghcr.io/$GHCR_OWNER/$IMAGE_NAME"
# Tag única por deploy (data + commit): mesma tag não gera revisão nova no Container App.
IMAGE_TAG="$(date +%Y%m%d-%H%M%S)-$(git -C .. rev-parse --short HEAD 2>/dev/null || echo local)"
IMAGE="$IMAGE_REPO:$IMAGE_TAG"
# Liga o pacote ao repositório na página do GitHub (opcional, só informativo).
SOURCE_URL=$(echo "$REPO_URL" | sed -E 's#^git@github\.com:#https://github.com/#; s#\.git$##')

echo "==> [1/6] Resource group: $RESOURCE_GROUP ($LOCATION)"
az group create -n "$RESOURCE_GROUP" -l "$LOCATION" -o none

echo "==> [2/6] Build da imagem (Docker local, contexto = raiz do repo): $IMAGE"
docker build --platform linux/amd64 \
    ${SOURCE_URL:+--label "org.opencontainers.image.source=$SOURCE_URL"} \
    -t "$IMAGE" -t "$IMAGE_REPO:latest" ..

# O pacote é público: a imagem não pode levar o modelo treinado (o .dockerignore
# exclui a pasta; esta conferência pega um .dockerignore quebrado ANTES do push).
if docker run --rm --entrypoint sh "$IMAGE" -c 'ls -A /app/src/correction/hybrid/artifacts 2>/dev/null | grep -q .'; then
    echo "ERRO: a imagem contém os artefatos do modelo e seria publicada. Confira o .dockerignore." >&2
    exit 1
fi

echo "==> [3/6] Push para o GHCR"
if ! docker push -q "$IMAGE" || ! docker push -q "$IMAGE_REPO:latest"; then
    cat >&2 <<EOF
ERRO: o push para o ghcr.io falhou. Faça login uma vez com um token que tenha
o escopo write:packages e rode de novo:
    gh auth refresh -h github.com -s write:packages
    gh auth token | docker login ghcr.io -u $GHCR_OWNER --password-stdin
EOF
    exit 1
fi

# O Container App puxa a imagem SEM credenciais: o pacote precisa estar público.
# Confere como um cliente anônimo (token anônimo + manifesto da tag recém-enviada).
ANON_TOKEN=$(curl -fsS "https://ghcr.io/token?scope=repository:$GHCR_OWNER/$IMAGE_NAME:pull" 2>/dev/null \
    | sed -nE 's/.*"token":"([^"]+)".*/\1/p' || true)
if [ -z "$ANON_TOKEN" ] || ! curl -fsS -o /dev/null -H "Authorization: Bearer $ANON_TOKEN" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json" \
    "https://ghcr.io/v2/$GHCR_OWNER/$IMAGE_NAME/manifests/$IMAGE_TAG" 2>/dev/null; then
    cat >&2 <<EOF
ERRO: a imagem foi enviada, mas o pacote está PRIVADO, e o Container App não
conseguiria baixá-la. Torne-o público uma vez (o GitHub só permite pela web):
    https://github.com/users/$GHCR_OWNER/packages/container/$IMAGE_NAME/settings
    → "Danger Zone" → "Change visibility" → Public
Depois rode o deploy de novo.
EOF
    exit 1
fi

echo "==> [4/6] Deployment do Bicep"
OUTPUTS=$(az deployment group create \
    -g "$RESOURCE_GROUP" \
    --template-file main.bicep \
    --query "[properties.outputs.fqdn.value, properties.outputs.storageAccountNameOut.value, properties.outputs.artifactsContainerOut.value]" \
    -o tsv \
    --parameters \
        appName="$APP_NAME" \
        existingEnvironmentId="$EXISTING_ENV_ID" \
        containerImage="$IMAGE" \
        redisUrl="$REDIS_URL" \
        redisNamespace="${REDIS_NAMESPACE:-}" \
        telegramBotToken="$TELEGRAM_BOT_TOKEN" \
        telegramWebhookSecret="${TELEGRAM_WEBHOOK_SECRET:-}" \
        adminTelegramChatId="${ADMIN_TELEGRAM_CHAT_ID:-}" \
        mistralApiKey="$MISTRAL_API_KEY" \
        correctionProvider="${CORRECTION_PROVIDER:-deepseek}" \
        correctionModel="${CORRECTION_MODEL:-deepseek-flash}" \
        correctionEffort="${CORRECTION_EFFORT:-high}" \
        correctionMode="${CORRECTION_MODE:-llm}" \
        jevModel="${JEV_MODEL:-jev-1.14.0}" \
        jevApiKey="${JEV_API_KEY:-}" \
        deepseekApiKey="${DEEPSEEK_API_KEY:-}" \
        googleApiKey="${GOOGLE_API_KEY:-}" \
        anthropicApiKey="${ANTHROPIC_API_KEY:-}" \
        openaiApiKey="${OPENAI_API_KEY:-}" \
        maritacaApiKey="${MARITACA_API_KEY:-}" \
        langfusePublicKey="${LANGFUSE_PUBLIC_KEY:-}" \
        langfuseSecretKey="${LANGFUSE_SECRET_KEY:-}" \
        langfuseHost="${LANGFUSE_HOST:-https://cloud.langfuse.com}")
read -r FQDN STORAGE_ACCOUNT ARTIFACTS_CONTAINER <<< "$(echo "$OUTPUTS" | tr '\n' ' ')"

if [ "$CORRECTION_MODE" = "hibrido" ]; then
    echo "==> [5/6] Artefatos do modelo → Blob PRIVADO ($STORAGE_ACCOUNT/$ARTIFACTS_CONTAINER)"
    # O app baixa ao iniciar e, se ainda não houver, antes da 1ª correção híbrida
    # (ver src/correction/hybrid/artifacts.py) — por isso pode subir antes do upload.
    az storage blob upload-batch --account-name "$STORAGE_ACCOUNT" --auth-mode key \
        -d "$ARTIFACTS_CONTAINER" -s "$ARTIFACTS_DIR" --pattern '[!.]*' \
        --overwrite --only-show-errors -o none
else
    echo "==> [5/6] Modo llm: sem artefatos do modelo para enviar"
fi

echo "==> [6/6] setWebhook do Telegram → https://$FQDN/v1/webhook/telegram"
RESP=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
    --data-urlencode "url=https://$FQDN/v1/webhook/telegram" \
    ${TELEGRAM_WEBHOOK_SECRET:+--data-urlencode "secret_token=${TELEGRAM_WEBHOOK_SECRET}"})
echo "    Telegram: $RESP"

echo ""
echo "✅ Pronto. App: https://$FQDN"
echo "   Imagem: $IMAGE"
echo "   Logs:  az containerapp logs show -n $APP_NAME -g $RESOURCE_GROUP --follow"

# Deploys antigos criavam um ACR Basic, que cobra uma diária fixa mesmo parado.
# Só avisa; apagar é decisão de quem roda o deploy, depois de conferir o app.
OLD_ACR=$(az acr list -g "$RESOURCE_GROUP" --query "[].name" -o tsv 2>/dev/null || true)
if [ -n "$OLD_ACR" ]; then
    echo ""
    echo "⚠️  Ainda existe um Azure Container Registry neste resource group (cobra diária fixa):"
    for acr in $OLD_ACR; do
        echo "    $acr  →  depois de conferir o app: az acr delete -n $acr -g $RESOURCE_GROUP --yes"
    done
fi

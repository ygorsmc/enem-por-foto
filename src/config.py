from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração central (env vars / .env). Documentação em .env.example."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "local" desliga a verificação de assinatura dos webhooks (dev/simulador).
    ENVIRONMENT: str = Field(default="local")
    LOG_LEVEL: str = Field(default="INFO")

    # Telegram é o canal recomendado (gratuito): a partir de 01/10/2026 o
    # WhatsApp Business Platform passa a cobrar por mensagem de serviço.
    CHANNEL_BACKEND: str = Field(default="telegram")
    MAX_TEXT_MESSAGE_LENGTH: int = Field(default=4000)

    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    # Prefixo opcional aplicado a TODAS as chaves Redis. Útil quando o mesmo
    # Redis é compartilhado entre múltiplos ambientes/deploys, evitando colisão
    # de chave entre eles. Vazio = sem prefixo (comportamento padrão).
    REDIS_NAMESPACE: str = Field(default="")

    # Backend de despacho de job: como o webhook entrega o trabalho ao passo OCR+LLM.
    #   "memory" (default): asyncio.create_task no mesmo processo — o modo mono-
    #     contêiner clássico (minReplicas=1). Usado por dev, simulador e testes.
    #   "azure": enfileira numa Azure Storage Queue drenada por um worker. É isso
    #     que permite o Azure Container Apps escalar pra ZERO com um KEDA
    #     azure-queue scaler. EXIGE Redis externo (Upstash). Ver deploy/README.md.
    QUEUE_BACKEND: str = Field(default="memory")  # memory | azure
    AZURE_STORAGE_CONNECTION_STRING: str = Field(default="")
    ESSAY_QUEUE_NAME: str = Field(default="essay-jobs")
    # Precisa exceder o pior caso de processamento (download + OCR + retries do
    # LLM): enquanto uma mensagem está sendo processada ela fica invisível; se
    # isso expirar antes do worker apagá-la, o job reentrega e reprocessa
    # (custo em dobro).
    QUEUE_VISIBILITY_TIMEOUT: int = Field(default=300)  # segundos
    QUEUE_POLL_INTERVAL: int = Field(default=3)         # segundos entre polls vazios

    # WhatsApp Cloud API (Meta)
    WHATSAPP_API_URL: str = Field(default="https://graph.facebook.com/v21.0")
    PHONE_NUMBER_ID: str = Field(default="")
    WHATSAPP_TOKEN: str = Field(default="")
    META_APP_SECRET: str = Field(default="")
    META_VERIFY_TOKEN: str = Field(default="")

    # Telegram Bot API
    TELEGRAM_BOT_TOKEN: str = Field(default="")
    TELEGRAM_WEBHOOK_SECRET: str = Field(default="")

    # OCR (Mistral) e correção (provedor plugável — ver src/correction/factory.py)
    MISTRAL_API_KEY: str = Field(default="")
    CORRECTION_PROVIDER: str = Field(default="deepseek")  # gemini | claude | openai | deepseek | maritaca
    CORRECTION_MODEL: str = Field(default="deepseek-v4-flash")  # nome do modelo NO provedor acima
    CORRECTION_EFFORT: str = Field(default="max")  # claude e deepseek: low | medium | high | max
    GOOGLE_API_KEY: str = Field(default="")
    ANTHROPIC_API_KEY: str = Field(default="")
    OPENAI_API_KEY: str = Field(default="")
    DEEPSEEK_API_KEY: str = Field(default="")
    MARITACA_API_KEY: str = Field(default="")

    # Limites do fluxo
    ESSAY_DAILY_LIMIT: int = Field(default=2)     # correções/aluno/dia (fluxo caro)
    MIN_ESSAY_CHARS: int = Field(default=120)     # OCR abaixo disso = foto ilegível
    MAX_ESSAY_PHOTOS: int = Field(default=2)      # partes de foto por redação (frente/verso)
    FLOW_TTL_SECONDS: int = Field(default=2700)   # 45 min para concluir o fluxo
    OCR_PREVIEW_MAX_CHARS: int = Field(default=3000)
    # Palavra do OCR abaixo deste score (0-1) entra na lista de "conferir" do preview.
    OCR_CONFIDENCE_THRESHOLD: float = Field(default=0.85)


settings = Settings()

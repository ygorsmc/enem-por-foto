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

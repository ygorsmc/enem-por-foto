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
    QUEUE_POLL_INTERVAL: int = Field(default=3)  # segundos entre polls vazios
    # Mensagens processadas em paralelo pelo worker da fila (uma task cada, como no backend
    # memory). O trabalho é quase todo espera de rede (OCR, Jev, LLM), então 0,5 vCPU aguenta.
    QUEUE_MAX_CONCURRENCY: int = Field(default=8)

    # WhatsApp Cloud API (Meta)
    WHATSAPP_API_URL: str = Field(default="https://graph.facebook.com/v25.0")
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
    CORRECTION_MODEL: str = Field(default="deepseek-flash")  # nome do modelo NO provedor acima
    # claude: low | medium | high | max · deepseek (V4.1): low | high | max
    # high: mesma acurácia do max nas medições (p = 0,83) com ~metade dos tokens de saída (o que o DeepSeek cobra)
    CORRECTION_EFFORT: str = Field(default="high")
    # Teto de tokens de SAÍDA por chamada ao LLM (raciocínio incluído). Medido em 100 correções do DeepSeek
    # high: mediana 9,3 mil, máximo 16,4 mil — 32 mil é o dobro do máximo. Sem teto, uma imagem com instruções
    # para "escrever sem parar" levaria a chamada ao limite da API (~390 mil tokens, ~US$ 0,47 no pico).
    LLM_MAX_OUTPUT_TOKENS: int = Field(default=32000)
    GOOGLE_API_KEY: str = Field(default="")
    ANTHROPIC_API_KEY: str = Field(default="")
    OPENAI_API_KEY: str = Field(default="")
    DEEPSEEK_API_KEY: str = Field(default="")
    MARITACA_API_KEY: str = Field(default="")

    # Modo da correção: "llm" (o LLM dá a nota e o feedback — padrão) ou "hibrido" (a nota vem do modelo
    # calibrado sobre as respostas do Jev, ver src/correction/hybrid/, e o LLM só escreve o feedback).
    CORRECTION_MODE: str = Field(default="llm")
    JEV_API_KEY: str = Field(default="")  # TypeSafe AI (Jev) — só usado no modo híbrido
    JEV_MODEL: str = Field(default="jev-1.14.0")
    # Só na nuvem: link SAS (só leitura) do contêiner privado do Blob com os artefatos do modelo; criado pelo
    # deploy (Bicep). Local, os artefatos vêm da pasta montada pelo docker-compose e isto fica vazio.
    HYBRID_ARTIFACTS_URL: str = Field(default="")

    # Observabilidade de custo (opcional — ver src/observability.py): liga com as duas chaves. O Langfuse recebe
    # só números (tokens, custo, tempo, modo), nunca texto da redação nem identificador do aluno.
    LANGFUSE_PUBLIC_KEY: str = Field(default="")
    LANGFUSE_SECRET_KEY: str = Field(default="")
    LANGFUSE_HOST: str = Field(default="https://cloud.langfuse.com")  # EU; US: https://us.cloud.langfuse.com

    # Limites do fluxo
    ESSAY_DAILY_LIMIT: int = Field(default=10)  # correções/aluno/dia (fluxo caro)
    # Leituras de foto (OCR, pago) por correção permitida: o limite diário de fotos é isto × ESSAY_DAILY_LIMIT.
    # Sem ele, quem ainda tem cota mandava fotos sem fim sem nunca confirmar (o contador de correção só sobe
    # na confirmação).
    PHOTOS_PER_ESSAY: int = Field(default=3)

    # Alerta de uso para o dono do bot (src/usage_alerts.py): mensagem no Telegram a cada N tokens do LLM de
    # correção. Só contadores agregados no Redis (tokens, chamadas, US$) — nada do aluno. Vazio = desligado.
    ADMIN_TELEGRAM_CHAT_ID: str = Field(default="")
    USAGE_ALERT_EVERY_TOKENS: int = Field(default=1_000_000)  # ~60 correções
    MIN_ESSAY_CHARS: int = Field(default=120)  # OCR abaixo disso = foto ilegível
    MAX_ESSAY_PHOTOS: int = Field(default=2)  # partes de foto por redação (frente/verso)
    FLOW_TTL_SECONDS: int = Field(default=2700)  # 45 min para concluir o fluxo
    OCR_PREVIEW_MAX_CHARS: int = Field(default=3000)
    # Palavra do OCR abaixo deste score (0-1) entra na lista de "conferir" do preview.
    OCR_CONFIDENCE_THRESHOLD: float = Field(default=0.85)
    # "-latest" acompanha a versão mais nova (em 2026-11-18, o OCR 4.1). Escolha do dono do projeto, ciente
    # do teste de 2026-11-18: o 4.1 empatou com o OCR 3 (mistral-ocr-2512) nas letras legíveis, mas em letra
    # difícil pode entrar em loop no fim do texto ("5,6,7,…,100") — barrado por ocr.looks_degenerate, e o
    # aluno é orientado a mandar outra foto. Para fixar a versão: OCR_MODEL=mistral-ocr-2512.
    OCR_MODEL: str = Field(default="mistral-ocr-latest")


settings = Settings()

"""Conexão Redis compartilhada + idempotência de webhook.

O Redis guarda TODO o estado do produto (não há banco relacional). As chaves,
opcionalmente prefixadas por REDIS_NAMESPACE (ver redis_key):
  - flow:{canal}:{sender}      → estado da conversa (JSON, TTL 45 min)
  - consent:{canal}:{sender}   → aceite LGPD (sem TTL)
  - essay_count:{canal}:{sender}:{yyyymmdd} → rate-limit diário
  - webhook:{message_id}       → idempotência (provedores reenviam updates)
"""

import structlog

from src.config import settings

logger = structlog.get_logger(__name__)

_redis = None


def redis_key(*parts: str) -> str:
    """Monta uma chave Redis aplicando o REDIS_NAMESPACE configurado. Útil quando
    o mesmo Redis é compartilhado entre múltiplos ambientes/deploys, evitando
    colisão de chave entre eles. Vazio = sem prefixo."""
    joined = ":".join(parts)
    return f"{settings.REDIS_NAMESPACE}:{joined}" if settings.REDIS_NAMESPACE else joined


async def get_redis():
    global _redis
    if _redis is None:
        from redis.asyncio import from_url
        _redis = from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def is_duplicate_message(message_id: str) -> bool:
    """True se este message_id já foi processado (Meta/Telegram reenviam updates
    quando o webhook demora ou reinicia). SETNX com TTL de 5 min."""
    redis = await get_redis()
    is_new = await redis.set(redis_key("webhook", message_id), "1", nx=True, ex=300)
    return not is_new

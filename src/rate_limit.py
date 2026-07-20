"""Rate-limit diário de correções por remetente.

A correção é o fluxo caro do produto (OCR Mistral + LLM por redação) e o acesso
é aberto (qualquer número da escola) — o limite diário é a única contenção de
custo. Contado por (canal, remetente, dia UTC); a chave expira sozinha em 24h.
"""

from datetime import datetime, timezone

from src.config import settings
from src.redis_client import get_redis, redis_key


def daily_count_key(channel_name: str, sender_id: str, now: datetime | None = None) -> str:
    """Chave do contador diário (pura, testável)."""
    day = (now or datetime.now(timezone.utc)).strftime("%Y%m%d")
    return redis_key("essay_count", channel_name, sender_id, day)


async def check_and_increment(channel_name: str, sender_id: str) -> bool:
    """Consome 1 correção do dia. True = pode corrigir; False = limite atingido."""
    redis = await get_redis()
    key = daily_count_key(channel_name, sender_id)
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 24 * 3600)
    return count <= settings.ESSAY_DAILY_LIMIT


async def has_quota(channel_name: str, sender_id: str) -> bool:
    """Só espia a cota (sem consumir) — usado antes do OCR, pra não gastar
    Mistral à toa quando a correção nem vai rolar."""
    redis = await get_redis()
    count = await redis.get(daily_count_key(channel_name, sender_id))
    return int(count or 0) < settings.ESSAY_DAILY_LIMIT

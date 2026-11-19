"""Rate-limit diário por remetente: correções e leituras de foto.

A correção é o fluxo caro do produto (OCR Mistral + LLM por redação) e o acesso
é aberto (qualquer pessoa com o link do bot) — os limites diários são a contenção
de custo por aluno. Contados por (canal, remetente, dia UTC); as chaves expiram
sozinhas em 24h.
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


def daily_photo_limit() -> int:
    """Leituras de foto por dia: PHOTOS_PER_ESSAY por correção permitida."""
    return settings.PHOTOS_PER_ESSAY * settings.ESSAY_DAILY_LIMIT


def daily_photo_key(channel_name: str, sender_id: str, now: datetime | None = None) -> str:
    day = (now or datetime.now(timezone.utc)).strftime("%Y%m%d")
    return redis_key("photo_count", channel_name, sender_id, day)


async def consume_photo_read(channel_name: str, sender_id: str) -> bool:
    """Consome 1 leitura de foto do dia (OCR é pago). True = pode ler; False = limite atingido.

    Conta toda foto que chega ao OCR, inclusive as ilegíveis e as que o aluno refaz: cada uma é uma
    chamada paga. O contador de correção só sobe na confirmação, então sem este limite quem ainda tem
    cota podia mandar fotos sem fim sem nunca corrigir."""
    redis = await get_redis()
    key = daily_photo_key(channel_name, sender_id)
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 24 * 3600)
    return count <= daily_photo_limit()

"""Alerta de uso do LLM de correção para o dono do bot.

A cada USAGE_ALERT_EVERY_TOKENS tokens (entrada + saída, raciocínio incluído) acumulados, o bot manda uma
mensagem no Telegram para ADMIN_TELEGRAM_CHAT_ID com o total de tokens, de chamadas e o custo em US$. O bot é
aberto ao público, então isso avisa cedo se o uso disparar.

Por que não os alertas do Langfuse: eles vigiam médias/contagens numa janela de tempo (não marcos acumulados
como "a cada 100 mil tokens"), notificam por Slack/webhook/PagerDuty (sem Telegram nem e-mail) e o plano grátis
permite 2. O Langfuse segue útil para os gráficos de custo (src/observability.py).

Guarda só contadores AGREGADOS no Redis, sem TTL e sem nada do aluno (nem id, nem texto) — pedido do dono do
projeto em 2026-11-18, não é histórico de uso. Falha aqui nunca atrapalha a correção: tudo é engolido e logado.
"""

import structlog

from src import messages as m
from src.config import settings
from src.redis_client import get_redis, redis_key

logger = structlog.get_logger(__name__)


def crossed_milestone(total: int, added: int, step: int) -> int | None:
    """Marco (múltiplo de `step`) cruzado ao somar `added` e chegar em `total`; None se nenhum.

    Se uma chamada cruzar mais de um marco de uma vez, devolve o maior (um alerta só)."""
    if step <= 0 or added <= 0:
        return None
    if total // step > (total - added) // step:
        return (total // step) * step
    return None


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


async def record_llm_usage(provider: str, tokens: int, cost_usd: float | None) -> None:
    """Soma o uso de UMA chamada ao LLM e avisa o dono se cruzou um marco de tokens."""
    if tokens <= 0:
        return
    try:
        redis = await get_redis()
        total = int(await redis.incrby(redis_key("usage", "llm_tokens"), tokens))
        calls = int(await redis.incr(redis_key("usage", "llm_calls")))
        cost_total = float(await redis.incrbyfloat(redis_key("usage", "llm_cost_usd"), cost_usd or 0.0))
        milestone = crossed_milestone(total, tokens, settings.USAGE_ALERT_EVERY_TOKENS)
        if milestone is None or not settings.ADMIN_TELEGRAM_CHAT_ID:
            return
        from src.channels.factory import get_channel  # tardio: evita ciclo de import com os canais

        text = m.USAGE_ALERT.format(
            provider=m.PROVIDER_NAMES.get(provider, provider),
            milestone=_milhar(milestone),
            total=_milhar(total),
            calls=_milhar(calls),
            cost=f"{cost_total:.2f}".replace(".", ","),
        )
        await get_channel("telegram").send_text(settings.ADMIN_TELEGRAM_CHAT_ID, text)
        logger.info("usage_alert_sent", milestone=milestone, calls=calls, cost_usd=round(cost_total, 4))
    except Exception as e:
        logger.warning("usage_alert_failed", error_type=type(e).__name__)

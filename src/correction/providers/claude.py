"""Corretor via Claude (Anthropic). Cache de contexto explícito via
`cache_control` no bloco de sistema — ~90% mais barato nas chamadas seguintes
dentro do TTL (1h aqui; o mínimo padrão da API é 5min). Ao contrário do
Gemini, não há objeto de cache separado para criar/gerenciar: o mesmo bloco
de sistema, byte a byte, em toda chamada, já é reconhecido como cache hit
pela própria API — cache_creation_input_tokens/cache_read_input_tokens no
usage de cada resposta são a única forma de confirmar isso de verdade (log
essay_corrected_claude_usage, abaixo).
"""

import anthropic
import structlog

from src.config import settings
from src.correction.interfaces import ICorrector
from src.prompts import ENEM_CORRECTION_SYSTEM

DEFAULT_MODEL = "claude-sonnet-5"

logger = structlog.get_logger(__name__)


class ClaudeCorrector(ICorrector):
    provider_name = "claude"

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY não configurada.")
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def correct(self, input_block: str) -> str:
        model = settings.CORRECTION_MODEL or DEFAULT_MODEL
        response = await self._client.messages.create(
            model=model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": settings.CORRECTION_EFFORT},
            system=[
                {
                    "type": "text",
                    "text": ENEM_CORRECTION_SYSTEM,
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }
            ],
            messages=[{"role": "user", "content": input_block}],
        )
        usage = response.usage
        logger.info(
            "essay_corrected_claude_usage",
            model=model,
            effort=settings.CORRECTION_EFFORT,
            input_tokens=usage.input_tokens,
            cache_creation_input_tokens=usage.cache_creation_input_tokens,
            cache_read_input_tokens=usage.cache_read_input_tokens,
            output_tokens=usage.output_tokens,
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        if not text:
            raise ValueError("Resposta vazia do modelo de correção")
        return text

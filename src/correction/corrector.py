"""Correção da redação: monta o bloco dinâmico do prompt (str.format, nunca
f-string) e delega a um dos provedores de LLM configuráveis
(CORRECTION_PROVIDER — ver src/correction/factory.py). Retry com backoff
exponencial — comum a sobrecarga (503) e limite de cota (429) em qualquer
provedor."""

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.correction.factory import get_corrector
from src.prompts import ENEM_CORRECTION_INPUT, NO_MOTIVATORS

logger = structlog.get_logger(__name__)

# Tetos de entrada: uma redação do ENEM tem ~30 linhas (~2.500 chars); os tetos
# são folgados e existem só para conter abuso/acidente (foto do livro inteiro).
MAX_THEME_CHARS = 500
MAX_MOTIVATORS_CHARS = 8000
MAX_ESSAY_CHARS = 8000


def build_correction_prompt(theme: str, motivators: str | None, essay_text: str) -> str:
    """Bloco dinâmico da correção — TEMA/TEXTOS MOTIVADORES/REDAÇÃO (puro,
    testável). O bloco estático (ENEM_CORRECTION_SYSTEM) é responsabilidade
    de cada provedor combinar do jeito mais barato (cache ou concatenação)."""
    return ENEM_CORRECTION_INPUT.format(
        tema=theme.strip()[:MAX_THEME_CHARS],
        textos_motivadores=(motivators or "").strip()[:MAX_MOTIVATORS_CHARS] or NO_MOTIVATORS,
        texto_redacao=essay_text.strip()[:MAX_ESSAY_CHARS],
    )


@retry(wait=wait_exponential(multiplier=2, min=4, max=60), stop=stop_after_attempt(4), reraise=True)
async def correct_essay(theme: str, motivators: str | None, essay_text: str) -> str:
    """Corrige a redação e retorna o feedback formatado para WhatsApp."""
    input_block = build_correction_prompt(theme, motivators, essay_text)
    feedback = await get_corrector().correct(input_block)
    if not feedback:
        raise ValueError("Resposta vazia do modelo de correção")
    logger.info(
        "essay_corrected",
        provider=settings.CORRECTION_PROVIDER,
        model=settings.CORRECTION_MODEL,
        chars=len(feedback),
    )
    return feedback.strip()

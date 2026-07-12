"""Corretor via Gemini. Cache de contexto explícito (client.caches.create) para
o bloco estático (~6000 tokens) — reaproveitado entre chamadas dentro do TTL.

Se a criação do cache falhar (ex.: modelo abaixo do mínimo de tokens exigido
para caching, variável por geração de modelo), cai para o bloco estático
inline sem cache — mais caro, mas nunca quebra a correção por causa disso.
"""

import time

import structlog
from google import genai
from google.genai import types

from src.config import settings
from src.correction.interfaces import ICorrector
from src.prompts import ENEM_CORRECTION_SYSTEM

logger = structlog.get_logger(__name__)

# TTL do cache: cobre uma janela de uso sem pagar armazenamento ocioso à noite;
# recriado sob demanda quando expira.
CACHE_TTL_SECONDS = 3600


class GeminiCorrector(ICorrector):
    provider_name = "gemini"

    def __init__(self) -> None:
        if not settings.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY não configurada.")
        self._client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self._cache_name: str | None = None
        self._cache_expires_at: float = 0.0

    async def _get_cache_name(self) -> str | None:
        if self._cache_name and time.monotonic() < self._cache_expires_at:
            return self._cache_name
        try:
            cache = await self._client.aio.caches.create(
                model=settings.CORRECTION_MODEL,
                config=types.CreateCachedContentConfig(
                    contents=[ENEM_CORRECTION_SYSTEM],
                    ttl=f"{CACHE_TTL_SECONDS}s",
                ),
            )
            self._cache_name = cache.name
            self._cache_expires_at = time.monotonic() + CACHE_TTL_SECONDS - 60
            return self._cache_name
        except Exception as e:
            logger.warning("gemini_cache_create_failed", error=str(e)[:300])
            self._cache_name = None
            return None

    async def correct(self, input_block: str) -> str:
        cache_name = await self._get_cache_name()
        if cache_name:
            contents = [input_block]
            config = types.GenerateContentConfig(cached_content=cache_name)
        else:
            contents = [ENEM_CORRECTION_SYSTEM, input_block]
            config = None

        response = await self._client.aio.models.generate_content(
            model=settings.CORRECTION_MODEL,
            contents=contents,
            config=config,
        )
        if not response.text:
            raise ValueError("Resposta vazia do modelo de correção")
        return response.text

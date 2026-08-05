"""Corretor via APIs compatíveis com o formato OpenAI (OpenAI e DeepSeek — a
API do DeepSeek é um drop-in do cliente openai, só troca a base_url).

Cache de contexto automático nas duas: nenhuma chamada especial é necessária.
O bloco de sistema é idêntico, byte a byte, em toda chamada — ambos os
provedores reconhecem e cacheiam sozinhos prefixos repetidos acima de um
mínimo de tokens, cobrando uma fração do preço normal nas chamadas seguintes.

`reasoning_effort` gradua o "thinking mode" do DeepSeek V4 (Flash/Pro). Os
tokens de raciocínio (reasoning_content, nunca visto pelo aluno) são cobrados
como output — por isso ficam logados separados em
completion_tokens_details.reasoning_tokens.

ATENÇÃO — dois comportamentos medidos em 2026-08-04 no `deepseek-v4-flash`
(versão 0731), ambos DIFERENTES do que esta docstring afirmava antes:

- **Os quatro níveis são distintos.** A API não colapsa mais low/medium em
  high. Numa mesma redação: low=15 tokens de raciocínio, medium=11.572,
  high=12.654, max=14.011. `low` na prática desliga o raciocínio e corta a
  latência de ~2min para ~40s.
- **Effort vazio NÃO desliga o thinking.** O `if` abaixo deixa de enviar
  `reasoning_effort` e `thinking.enabled`, mas o modelo raciocina assim mesmo
  (12.525 tokens medidos) — e ainda por cima sem controle do nível. Se a
  intenção for gastar menos, use `low` explicitamente, não string vazia.

O nível afeta a NOTA, não só o custo: mais raciocínio correlaciona com correção
mais dura. Ver a comparação pareada em _local/docs_src/08_metricas_performance_e_roi.md.
"""

import structlog
from openai import AsyncOpenAI

from src.correction.interfaces import ICorrector
from src.prompts import ENEM_CORRECTION_SYSTEM

logger = structlog.get_logger(__name__)


class OpenAICompatibleCorrector(ICorrector):
    def __init__(
        self,
        provider_name: str,
        api_key: str,
        model: str,
        base_url: str | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(f"Chave de API não configurada para o provedor '{provider_name}'.")
        self.provider_name = provider_name
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def correct(self, input_block: str) -> str:
        extra_kwargs = {}
        if self._reasoning_effort:
            extra_kwargs["reasoning_effort"] = self._reasoning_effort
            extra_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": ENEM_CORRECTION_SYSTEM},
                {"role": "user", "content": input_block},
            ],
            **extra_kwargs,
        )

        usage = response.usage
        details = getattr(usage, "completion_tokens_details", None)
        logger.info(
            "essay_corrected_openai_compatible_usage",
            provider=self.provider_name,
            model=self._model,
            reasoning_effort=self._reasoning_effort,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            prompt_cache_hit_tokens=getattr(usage, "prompt_cache_hit_tokens", None),
            prompt_cache_miss_tokens=getattr(usage, "prompt_cache_miss_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            reasoning_tokens=getattr(details, "reasoning_tokens", None) if details else None,
        )

        text = response.choices[0].message.content
        if not text:
            raise ValueError("Resposta vazia do modelo de correção")
        return text

"""Corretor via APIs compatíveis com o formato OpenAI (OpenAI e DeepSeek — a
API do DeepSeek é um drop-in do cliente openai, só troca a base_url).

Cache de contexto automático nas duas: nenhuma chamada especial é necessária.
O bloco de sistema é idêntico, byte a byte, em toda chamada — ambos os
provedores reconhecem e cacheiam sozinhos prefixos repetidos acima de um
mínimo de tokens, cobrando uma fração do preço normal nas chamadas seguintes.

`reasoning_effort` gradua o "thinking mode" do DeepSeek. Os tokens de
raciocínio (reasoning_content, nunca visto pelo aluno) são cobrados como
output — por isso ficam logados separados em
completion_tokens_details.reasoning_tokens.

MODELO ATUAL (conferido em 2026-11-16 via `GET /models`): desde 10/09/2026 a
DeepSeek serve o **V4.1-Flash** com o id `deepseek-flash`. O id antigo
`deepseek-v4-flash` ainda responde, mas é só um apelido TEMPORÁRIO para o
V4.1 — trocar `CORRECTION_MODEL` antes que ele seja desligado. A API declara
os níveis `low | high | max` (padrão `high`); `medium` não dá erro, mas se
comporta como `high`. Raciocínio numa mesma redação (2026-11-16): low ~3,5 mil
tokens, medium ~5,2 mil, high ~4,0 mil, max ~17,3 mil.

Medido antes, no V4 Flash 0731 (2026-08-04), e não reconferido no V4.1:

- **Effort vazio NÃO desliga o thinking.** O `if` abaixo deixa de enviar
  `reasoning_effort` e `thinking.enabled`, mas o modelo raciocinava assim
  mesmo (12.525 tokens medidos), sem controle do nível. Se a intenção for
  gastar menos, use `low` explicitamente, não string vazia.
- O nível afetava a NOTA, não só o custo: mais raciocínio correlacionava com
  correção mais dura. Ver a comparação pareada em
  _local/docs_src/08_metricas_performance_e_roi.md.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from openai import AsyncOpenAI

from src import observability, usage_alerts
from src.correction import pricing
from src.correction.interfaces import ICorrector
from src.prompts import ENEM_CORRECTION_SYSTEM

logger = structlog.get_logger(__name__)


def _usage_and_cost(model: str, usage: Any, when: datetime) -> tuple[dict[str, int], dict[str, float] | None]:
    """Tokens no formato do Langfuse e custo em US$ (None se o modelo não tem tabela em `pricing`)."""
    if usage is None:
        return {}, None
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    output = getattr(usage, "completion_tokens", 0) or 0
    hit = getattr(usage, "prompt_cache_hit_tokens", None)  # DeepSeek
    if hit is None:  # OpenAI informa o cache em prompt_tokens_details
        hit = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", None)
    hit = hit or 0
    reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None) or 0
    details = {"input": prompt - hit, "input_cached_tokens": hit, "output": output, "total": prompt + output}
    if reasoning:
        details["output_reasoning_tokens"] = reasoning  # já contido em "output" (cobrado como saída)
    return details, pricing.llm_cost(model, hit, prompt - hit, output, when)


class OpenAICompatibleCorrector(ICorrector):
    def __init__(
        self,
        provider_name: str,
        api_key: str,
        model: str,
        base_url: str | None = None,
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
        max_tokens_param: str = "max_tokens",
    ) -> None:
        """`max_output_tokens`: teto de saída por chamada (raciocínio incluído); None = padrão da API.
        `max_tokens_param`: nome do campo no provedor (DeepSeek: max_tokens; OpenAI: max_completion_tokens)."""
        if not api_key:
            raise ValueError(f"Chave de API não configurada para o provedor '{provider_name}'.")
        self.provider_name = provider_name
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        self._max_tokens_param = max_tokens_param
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def correct(self, input_block: str) -> str:
        extra_kwargs = {}
        if self._reasoning_effort:
            extra_kwargs["reasoning_effort"] = self._reasoning_effort
            extra_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        if self._max_output_tokens:
            extra_kwargs[self._max_tokens_param] = self._max_output_tokens

        started = datetime.now(UTC)  # o preço do DeepSeek depende do horário (pico/fora do pico)
        with observability.generation(
            "llm", self._model, provider=self.provider_name, effort=self._reasoning_effort
        ) as gen:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": ENEM_CORRECTION_SYSTEM},
                    {"role": "user", "content": input_block},
                ],
                **extra_kwargs,
            )
            tokens, cost = _usage_and_cost(self._model, response.usage, started)
            window = pricing.price_window(started) if cost else None
            gen.update(usage_details=tokens, cost_details=cost, metadata={"price_window": window})

        logger.info(
            "essay_corrected_openai_compatible_usage",
            provider=self.provider_name,
            model=self._model,
            reasoning_effort=self._reasoning_effort,
            prompt_tokens=tokens.get("input", 0) + tokens.get("input_cached_tokens", 0),
            prompt_cache_hit_tokens=tokens.get("input_cached_tokens"),
            prompt_cache_miss_tokens=tokens.get("input"),
            completion_tokens=tokens.get("output"),
            reasoning_tokens=tokens.get("output_reasoning_tokens"),
            cost_usd=round(cost["total"], 6) if cost else None,
            price_window=window,
        )
        await usage_alerts.record_llm_usage(self.provider_name, tokens.get("total", 0), cost["total"] if cost else None)

        if getattr(response.choices[0], "finish_reason", None) == "length":
            # Bateu no teto de saída: o feedback chega cortado. Raro com 32 mil (2× o máximo medido).
            logger.warning(
                "llm_output_truncated",
                provider=self.provider_name,
                model=self._model,
                max_output_tokens=self._max_output_tokens,
            )
        text = response.choices[0].message.content
        if not text:
            raise ValueError("Resposta vazia do modelo de correção")
        return text

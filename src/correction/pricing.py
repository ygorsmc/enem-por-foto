"""Custo em US$ de cada chamada paga (LLM e Jev), pela tabela de preço do fornecedor.

Só alimenta o log e a observabilidade (Langfuse): nada no fluxo depende destes valores. Atualize as tabelas aqui
quando o fornecedor mudar o preço.

DeepSeek — tabela oficial do `deepseek-flash` (DeepSeek-V4.1-Flash-1017) e do `deepseek-v4-pro`, vista em
2026-11-17. Cobra em dois horários: PICO nos dias úteis, 01:00–04:00 e 06:00–10:00 UTC (horário comercial da
China; em Brasília, 22h–1h e 3h–7h); fora disso, metade do preço. Feriados chineses também contam como fora do pico,
mas não estão modelados: nesses dias o custo calculado sai acima do cobrado.

Jev (TypeSafe AI, `jev-1.14.0`): só a entrada é cobrada, US$ 0,042 por 1M de tokens (medido no laboratório:
US$ 0,007412 por 176.470 tokens); a saída é gratuita.

Modelos sem tabela (Gemini, Claude, OpenAI, Maritaca) → custo `None`: o log registra só os tokens.
"""

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class TokenPrice:
    """US$ por 1M de tokens."""

    cache_hit: float
    cache_miss: float
    output: float


_DEEPSEEK: dict[str, dict[str, TokenPrice]] = {
    "deepseek-flash": {"off_peak": TokenPrice(0.003, 0.15, 0.60), "peak": TokenPrice(0.006, 0.30, 1.20)},
    "deepseek-v4-pro": {"off_peak": TokenPrice(0.022, 0.66, 1.98), "peak": TokenPrice(0.044, 1.32, 3.96)},
}
# Nomes antigos que a DeepSeek ainda aceita e cobra pelo preço do Flash.
_ALIASES = {"deepseek-v4-flash": "deepseek-flash", "deepseek-v4-flash-vision-exp": "deepseek-flash"}
_PEAK_HOURS_UTC = ((1, 4), (6, 10))

JEV_USD_PER_M_INPUT = 0.042


def price_window(when: datetime | None = None) -> str:
    """Faixa de preço do DeepSeek no instante `when` (padrão: agora): "peak" ou "off_peak"."""
    t = (when or datetime.now(UTC)).astimezone(UTC)
    if t.weekday() >= 5:
        return "off_peak"
    return "peak" if any(start <= t.hour < end for start, end in _PEAK_HOURS_UTC) else "off_peak"


def llm_cost(
    model: str,
    cache_hit_tokens: int,
    cache_miss_tokens: int,
    output_tokens: int,
    when: datetime | None = None,
) -> dict[str, float] | None:
    """Custo por tipo de token (chaves no formato do Langfuse) mais "total"; None se o modelo não tem tabela.

    Os tokens de raciocínio já estão dentro de `output_tokens` e são cobrados como saída.
    """
    table = _DEEPSEEK.get(_ALIASES.get(model, model))
    if table is None:
        return None
    p = table[price_window(when)]
    parts = {
        "input_cached_tokens": cache_hit_tokens * p.cache_hit / 1e6,
        "input": cache_miss_tokens * p.cache_miss / 1e6,
        "output": output_tokens * p.output / 1e6,
    }
    parts["total"] = sum(parts.values())
    return parts


def jev_cost(input_tokens: int) -> dict[str, float]:
    cost = input_tokens * JEV_USD_PER_M_INPUT / 1e6
    return {"input": cost, "total": cost}

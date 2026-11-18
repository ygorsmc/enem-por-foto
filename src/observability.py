"""Uso e custo das chamadas pagas (LLM e Jev) no Langfuse — opcional.

Liga só com LANGFUSE_PUBLIC_KEY e LANGFUSE_SECRET_KEY. Sem elas, tudo aqui é no-op; os logs do structlog continuam
registrando tokens e custo de cada chamada. Uma correção vira um trace ("correcao") com uma observação por chamada
paga ("jev", "llm"). Falha no Langfuse nunca derruba a correção: vira log `langfuse_error`.

Privacidade (LGPD, público menor de idade) — duas travas que NÃO podem ser afrouxadas:
1. Só NÚMEROS saem daqui: modelo, tokens, custo, tempo e o modo de correção. Nunca o texto da redação, o tema, o
   feedback nem identificador do aluno. As funções deste módulo nem aceitam `input`/`output`.
2. TracerProvider PRÓPRIO, nunca o global. Por padrão o SDK do Langfuse instala um provider global de OpenTelemetry,
   e com ele o SDK do Mistral passa a criar spans das chamadas de OCR (que levam a foto da redação), que o filtro
   padrão do Langfuse exportaria (são spans "gen_ai"). Com provider privado, o Mistral não acha provider e não cria
   span nenhum; e o filtro `_only_langfuse_spans` só exporta os spans criados pelo próprio SDK do Langfuse.
"""

import contextlib
from collections.abc import Iterator
from typing import Any

import structlog

from src.config import settings

logger = structlog.get_logger(__name__)

_LANGFUSE_SCOPE = "langfuse-sdk"  # nome do tracer do SDK do Langfuse (langfuse._client.constants)
_client: Any = None
_init_done = False


def _only_langfuse_spans(span: Any) -> bool:
    scope = getattr(span, "instrumentation_scope", None)
    return scope is not None and scope.name == _LANGFUSE_SCOPE


def _get_client() -> Any:
    global _client, _init_done
    if _init_done:
        return _client
    _init_done = True
    if not (settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY):
        return None
    try:
        from langfuse import Langfuse  # tardio: sem chaves, o SDK nem é importado
        from opentelemetry.sdk.trace import TracerProvider

        _client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            base_url=settings.LANGFUSE_HOST,
            environment=settings.ENVIRONMENT.lower(),
            tracer_provider=TracerProvider(),  # privado: ver trava 2 no docstring do módulo
            should_export_span=_only_langfuse_spans,
        )
        logger.info("langfuse_enabled", host=settings.LANGFUSE_HOST)
    except Exception as e:
        logger.warning("langfuse_error", stage="init", error_type=type(e).__name__, error=str(e)[:200])
        _client = None
    return _client


class Generation:
    """Observação de uma chamada paga; `update` é no-op quando o Langfuse está desligado."""

    def __init__(self, obs: Any = None) -> None:
        self._obs = obs

    def update(
        self,
        *,
        usage_details: dict[str, int] | None = None,
        cost_details: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._obs is None:
            return
        try:
            self._obs.update(usage_details=usage_details, cost_details=cost_details, metadata=metadata)
        except Exception as e:
            logger.warning("langfuse_error", stage="update", error_type=type(e).__name__)


@contextlib.contextmanager
def _observation(**kwargs: Any) -> Iterator[Any]:
    """Abre uma observação no Langfuse, se ligado; qualquer falha do SDK vira log e a chamada segue."""
    client = _get_client()
    if client is None:
        yield None
        return
    with contextlib.ExitStack() as stack:
        obs = None
        try:
            obs = stack.enter_context(client.start_as_current_observation(**kwargs))
        except Exception as e:
            logger.warning("langfuse_error", stage="start", error_type=type(e).__name__)
        yield obs


@contextlib.contextmanager
def correction_trace(**metadata: str) -> Iterator[None]:
    """Agrupa as chamadas de uma correção num trace. `metadata`: só rótulos de configuração (modo, modelo)."""
    with _observation(name="correcao", as_type="span", metadata=metadata):
        yield


@contextlib.contextmanager
def generation(name: str, model: str, **metadata: Any) -> Iterator[Generation]:
    """Uma chamada paga. Envolva a chamada de rede (para o tempo sair certo) e chame `.update` com os números."""
    with _observation(name=name, as_type="generation", model=model, metadata=metadata or None) as obs:
        yield Generation(obs)


def shutdown() -> None:
    """Envia o que estiver pendente. Bloqueante: chame fora do event loop (asyncio.to_thread)."""
    if _client is None:
        return
    try:
        _client.shutdown()
    except Exception as e:
        logger.warning("langfuse_error", stage="shutdown", error_type=type(e).__name__)

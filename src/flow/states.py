"""Estado da conversa no Redis — a única memória do fluxo (não há banco).

Chave `flow:{canal}:{sender}` com JSON do FlowData e TTL de 45 min: fluxo
abandonado evapora sozinho, junto com o texto OCR (LGPD — nada persiste após
a correção). Ausência de chave = IDLE.

O consentimento LGPD (`consent:{canal}:{sender}`) fica FORA do FlowData e sem
TTL: é um aceite, não um passo do fluxo.
"""

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum

from src.config import settings
from src.redis_client import get_redis, redis_key


class FlowState(StrEnum):
    AWAITING_THEME = "awaiting_theme"
    AWAITING_MOTIVATORS = "awaiting_motivators"
    AWAITING_ESSAY_PHOTO = "awaiting_essay_photo"
    CONFIRMING = "confirming"
    # Aluno colando a versão corrigida à mão do texto OCR (letra difícil).
    EDITING_TEXT = "editing_text"


@dataclass
class FlowData:
    state: str
    theme: str = ""
    motivators: list[str] = field(default_factory=list)
    # Partes de texto OCR (uma por foto — redação fotografada em 2 folhas/verso).
    essay_parts: list[str] = field(default_factory=list)
    # Palavras que o OCR leu com baixa confiança (destacadas no preview p/ conferir).
    # Zeradas quando o aluno edita o texto à mão (ele já corrigiu a leitura).
    flagged_words: list[str] = field(default_factory=list)

    @property
    def essay_text(self) -> str:
        return "\n\n".join(self.essay_parts).strip()

    @property
    def motivators_text(self) -> str:
        return "\n\n".join(self.motivators).strip()


def _flow_key(channel_name: str, sender_id: str) -> str:
    return redis_key("flow", channel_name, sender_id)


def _consent_key(channel_name: str, sender_id: str) -> str:
    return redis_key("consent", channel_name, sender_id)


async def load_flow(channel_name: str, sender_id: str) -> FlowData | None:
    redis = await get_redis()
    raw = await redis.get(_flow_key(channel_name, sender_id))
    if not raw:
        return None
    data = json.loads(raw)
    return FlowData(**data)


async def save_flow(channel_name: str, sender_id: str, flow: FlowData) -> None:
    redis = await get_redis()
    await redis.set(
        _flow_key(channel_name, sender_id),
        json.dumps(asdict(flow), ensure_ascii=False),
        ex=settings.FLOW_TTL_SECONDS,
    )


async def clear_flow(channel_name: str, sender_id: str) -> None:
    redis = await get_redis()
    await redis.delete(_flow_key(channel_name, sender_id))


async def has_consent(channel_name: str, sender_id: str) -> bool:
    redis = await get_redis()
    return bool(await redis.get(_consent_key(channel_name, sender_id)))


async def grant_consent(channel_name: str, sender_id: str) -> None:
    redis = await get_redis()
    await redis.set(_consent_key(channel_name, sender_id), "1")

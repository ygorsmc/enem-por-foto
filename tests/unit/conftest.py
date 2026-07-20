"""Fixtures puras (sem I/O): Redis fake em memória + canal fake que grava envios."""

from typing import Any, Mapping

import pytest

import src.redis_client as redis_client
from src.channels.interfaces import IMessagingChannel, InboundMessage
from src.config import settings


class FakeRedis:
    """Só o que o projeto usa: get/set(nx,ex)/delete/incr/decr/expire."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        return True

    async def delete(self, key):
        self.store.pop(key, None)

    async def incr(self, key):
        val = int(self.store.get(key, "0")) + 1
        self.store[key] = str(val)
        return val

    async def decr(self, key):
        val = int(self.store.get(key, "0")) - 1
        self.store[key] = str(val)
        return val

    async def expire(self, key, seconds):
        return True


class FakeChannel(IMessagingChannel):
    """Grava tudo que o fluxo tentou enviar, para asserção nos testes."""

    channel_name = "fake"

    def __init__(self, media: bytes = b""):
        self.sent: list[tuple] = []       # ("text", corpo) | ("buttons", corpo, [ids])
        self.media = media

    async def send_text(self, user_id, text, reply_to=None) -> dict:
        self.sent.append(("text", text))
        return {}

    async def send_buttons(self, user_id, body, buttons, footer="") -> dict:
        self.sent.append(("buttons", body, [b["id"] for b in buttons]))
        return {}

    async def send_typing(self, user_id) -> None:
        pass

    async def download_media(self, media_id) -> bytes:
        return self.media

    def parse_inbound(self, raw_payload: dict) -> InboundMessage | None:
        return None

    async def verify_signature(self, body: bytes, headers: Mapping[str, str]) -> bool:
        return True

    def build_verification_response(self, query_params: Mapping[str, str]) -> Any:
        return None


@pytest.fixture(autouse=True)
def fake_redis():
    """Substitui a conexão global por um FakeRedis novo a cada teste, e zera o
    REDIS_NAMESPACE — os testes são determinísticos, independentes do .env do dev
    (que pode ter um namespace setado para dividir um Upstash entre bots)."""
    fake = FakeRedis()
    redis_client._redis = fake
    prev_ns = settings.REDIS_NAMESPACE
    settings.REDIS_NAMESPACE = ""
    yield fake
    settings.REDIS_NAMESPACE = prev_ns
    redis_client._redis = None


@pytest.fixture
def channel():
    return FakeChannel()


def text_msg(text: str, msg_id: str = "m1") -> InboundMessage:
    return InboundMessage(sender_id="aluno1", text=text, message_id=msg_id, message_type="text")


def image_msg(media_id: str = "media-1", caption: str = "", msg_id: str = "m2") -> InboundMessage:
    return InboundMessage(
        sender_id="aluno1", text=caption, message_id=msg_id, message_type="image", media_id=media_id
    )


def button_msg(btn_id: str, msg_id: str = "m3") -> InboundMessage:
    return InboundMessage(
        sender_id="aluno1", text="", message_id=msg_id, message_type="interactive",
        interactive_payload={"type": "button_reply", "id": btn_id, "title": btn_id},
    )

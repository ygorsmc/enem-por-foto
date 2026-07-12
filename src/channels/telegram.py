import hmac
from typing import Any, Mapping

import httpx
import structlog
from fastapi import Response

from src.channels.interfaces import IMessagingChannel, InboundMessage
from src.channels.text_utils import chunk_text
from src.config import settings

logger = structlog.get_logger(__name__)


class TelegramChannel(IMessagingChannel):
    """Implementação de canal para Telegram Bot API."""

    channel_name = "telegram"

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.secret_token = settings.TELEGRAM_WEBHOOK_SECRET
        self.max_length = settings.MAX_TEXT_MESSAGE_LENGTH

    async def _send_request(self, endpoint: str, payload: dict) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=f"{self.api_url}/{endpoint}",
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def send_text(self, user_id: str, text: str, reply_to: str | None = None) -> dict:
        # O Telegram REJEITA (400 "message is too long") acima de ~4096 chars —
        # a correção completa da redação sempre vem em várias mensagens.
        chunks = chunk_text(text, self.max_length)
        last_response: dict = {}
        for i, chunk in enumerate(chunks):
            if not chunk:
                continue

            payload: dict[str, Any] = {
                "chat_id": user_id,
                "text": chunk,
                "parse_mode": "Markdown",
            }

            if i == 0 and reply_to:
                payload["reply_to_message_id"] = int(reply_to) if str(reply_to).isdigit() else reply_to

            try:
                last_response = await self._send_request("sendMessage", payload)
            except httpx.HTTPStatusError as e:
                # O parser "Markdown" legado do Telegram exige entidades perfeitamente
                # balanceadas (*, _, `, [). Respostas livres do LLM ocasionalmente
                # contêm markdown malformado (ex.: um "_" solto) → 400 "can't parse
                # entities". Em vez de derrubar a entrega, reenviamos como texto puro.
                if e.response.status_code == 400:
                    logger.warning(
                        "telegram_markdown_fallback",
                        user_id=user_id,
                        detail=e.response.text[:300],
                    )
                    payload.pop("parse_mode", None)
                    last_response = await self._send_request("sendMessage", payload)
                else:
                    raise
        return last_response

    async def send_buttons(self, user_id: str, body: str, buttons: list[dict], footer: str = "") -> dict:
        full_text = body
        if footer:
            full_text += f"\n\n_{footer}_"

        # Um botão por linha para garantir que textos longos caibam.
        inline_keyboard = [
            [{"text": btn["title"], "callback_data": btn["id"]}]
            for btn in buttons
        ]

        payload = {
            "chat_id": user_id,
            "text": full_text,
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": inline_keyboard},
        }

        try:
            return await self._send_request("sendMessage", payload)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                logger.warning(
                    "telegram_markdown_fallback_buttons",
                    user_id=user_id,
                    detail=e.response.text[:300],
                )
                payload.pop("parse_mode", None)
                return await self._send_request("sendMessage", payload)
            raise

    async def send_typing(self, user_id: str) -> None:
        await self._send_request("sendChatAction", {"chat_id": user_id, "action": "typing"})

    async def download_media(self, media_id: str) -> bytes:
        """Baixa uma mídia recebida: getFile → file_path → bytes."""
        async with httpx.AsyncClient() as client:
            meta = await client.post(
                url=f"{self.api_url}/getFile", json={"file_id": media_id}, timeout=30.0
            )
            meta.raise_for_status()
            file_path = meta.json()["result"]["file_path"]
            resp = await client.get(
                url=f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}", timeout=60.0
            )
            resp.raise_for_status()
            return resp.content

    def parse_inbound(self, raw_payload: dict) -> InboundMessage | None:
        try:
            # Update pode ser Message ou CallbackQuery (botões inline).
            if "message" in raw_payload:
                msg = raw_payload["message"]
                chat_id = str(msg["chat"]["id"])
                msg_id = str(msg["message_id"])

                first_name = msg.get("from", {}).get("first_name", "")
                last_name = msg.get("from", {}).get("last_name", "")
                sender_name = f"{first_name} {last_name}".strip()

                # Foto (redação) — pega a maior resolução; caption vira text.
                if "photo" in msg and msg["photo"]:
                    media_id = msg["photo"][-1].get("file_id")
                    return InboundMessage(
                        sender_id=chat_id,
                        text=msg.get("caption", ""),
                        message_id=msg_id,
                        message_type="image",
                        sender_name=sender_name,
                        media_id=media_id,
                    )

                return InboundMessage(
                    sender_id=chat_id,
                    text=msg.get("text", ""),
                    message_id=msg_id,
                    message_type="text",
                    sender_name=sender_name,
                )

            elif "callback_query" in raw_payload:
                cb = raw_payload["callback_query"]
                chat_id = str(cb["message"]["chat"]["id"])
                msg_id = str(cb["message"]["message_id"])

                first_name = cb.get("from", {}).get("first_name", "")
                last_name = cb.get("from", {}).get("last_name", "")
                sender_name = f"{first_name} {last_name}".strip()

                data = cb.get("data", "")
                interactive_payload = {
                    "type": "button_reply",
                    "id": data,
                    # No callback do Telegram só chega o data, não o title.
                    "title": data,
                }

                return InboundMessage(
                    sender_id=chat_id,
                    text="",
                    message_id=msg_id,
                    message_type="interactive",
                    interactive_payload=interactive_payload,
                    sender_name=sender_name,
                )

        except KeyError:
            return None
        return None

    async def verify_signature(self, body: bytes, headers: Mapping[str, str]) -> bool:
        if settings.ENVIRONMENT == "local":
            return True

        # Telegram manda o secret token no header (registrado via setWebhook).
        token = headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not token or not self.secret_token:
            return False

        # Comparação em tempo constante (evita timing side-channel no secret).
        return hmac.compare_digest(token, self.secret_token)

    def build_verification_response(self, query_params: Mapping[str, str]) -> Any:
        # Telegram não faz challenge GET, só manda os POSTs.
        return Response(status_code=200)

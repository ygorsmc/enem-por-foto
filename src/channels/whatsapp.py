import asyncio
import hashlib
import hmac
from typing import Any, Mapping

import httpx
import structlog
from fastapi import Response

from src.channels.interfaces import IMessagingChannel, InboundMessage
from src.channels.markdown import to_whatsapp_markdown
from src.channels.text_utils import chunk_text
from src.config import settings

logger = structlog.get_logger(__name__)


class WhatsAppChannel(IMessagingChannel):
    """Implementação de canal para WhatsApp Cloud API."""

    channel_name = "whatsapp"
    # Corpo de mensagem interativa (botões): limite RÍGIDO da Meta. Acima disso
    # a API rejeita com 400 — o excedente vai como send_text antes.
    INTERACTIVE_BODY_LIMIT = 1024

    def __init__(self):
        self.api_url = settings.WHATSAPP_API_URL
        self.phone_number_id = settings.PHONE_NUMBER_ID
        self.access_token = settings.WHATSAPP_TOKEN
        self.app_secret = settings.META_APP_SECRET
        self.verify_token = settings.META_VERIFY_TOKEN
        self.max_length = settings.MAX_TEXT_MESSAGE_LENGTH

    async def _send_request(self, message: dict) -> dict:
        """Envio interno para a Graph API.

        Em erro, a Meta detalha o motivo (parâmetro inválido, janela de 24h
        fechada, etc.) no CORPO JSON da resposta — que `raise_for_status()`
        descarta, deixando só "400 Bad Request". Logamos o corpo ANTES de
        propagar, para o motivo do 4xx/5xx nunca ficar invisível."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=f"{self.api_url}/{self.phone_number_id}/messages",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json=message,
                timeout=30.0,
            )
            if response.is_error:
                logger.error(
                    "whatsapp_api_error",
                    status=response.status_code,
                    msg_type=message.get("type"),
                    body=response.text[:800],
                )
            response.raise_for_status()
            return response.json()

    async def send_text(self, user_id: str, text: str, reply_to: str | None = None) -> dict:
        text = to_whatsapp_markdown(text)
        chunks = chunk_text(text, self.max_length)
        last_response: dict = {}
        for i, chunk in enumerate(chunks):
            if not chunk:
                continue

            message = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": user_id,
                "type": "text",
                "text": {"body": chunk},
            }

            if i == 0 and reply_to:
                message["context"] = {"message_id": reply_to}

            last_response = await self._send_request(message)

            if i < len(chunks) - 1:
                await asyncio.sleep(0.5)

        return last_response

    async def send_buttons(self, user_id: str, body: str, buttons: list[dict], footer: str = "") -> dict:
        if not buttons:
            # Sem botões a Meta rejeita com 400 opaco — falha cedo e legível.
            raise ValueError("Reply Buttons exigem ao menos 1 opção no WhatsApp")
        if len(buttons) > 3:
            raise ValueError("Reply Buttons suportam no máximo 3 opções no WhatsApp")

        body = to_whatsapp_markdown(body)
        if len(body) > self.INTERACTIVE_BODY_LIMIT:
            # Corpo > 1024 (a Meta rejeita): manda o conteúdo completo como texto
            # e deixa os botões com um prompt curto. Nada se perde.
            await self.send_text(user_id, body)
            body = "👇 Escolha uma opção:"

        message: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": user_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": btn["id"], "title": btn["title"][:20]},
                        }
                        for btn in buttons
                    ]
                },
            },
        }
        if footer:
            message["interactive"]["footer"] = {"text": footer}

        return await self._send_request(message)

    async def send_typing(self, user_id: str) -> None:
        # WhatsApp Cloud API não suporta indicador de typing direto.
        pass

    async def download_media(self, media_id: str) -> bytes:
        """Baixa uma mídia recebida: GET /media_id → url assinada → bytes."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient() as client:
            meta = await client.get(f"{self.api_url}/{media_id}", headers=headers, timeout=30.0)
            meta.raise_for_status()
            url = meta.json()["url"]
            resp = await client.get(url, headers=headers, timeout=60.0)
            resp.raise_for_status()
            return resp.content

    def parse_inbound(self, raw_payload: dict) -> InboundMessage | None:
        try:
            entry = raw_payload.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})

            if "messages" not in value:
                return None

            msg_data = value["messages"][0]
            phone = msg_data["from"]
            msg_type = msg_data["type"]
            msg_id = msg_data["id"]

            sender_name = ""
            contacts = value.get("contacts", [])
            if contacts:
                sender_name = contacts[0].get("profile", {}).get("name", "")

            text = msg_data.get("text", {}).get("body", "") if msg_type == "text" else ""
            interactive_payload = None
            media_id = None

            # Foto (redação) — o caption vira o text; download na task de background.
            if msg_type == "image":
                media_id = msg_data.get("image", {}).get("id")
                text = msg_data.get("image", {}).get("caption", "")

            if msg_type == "interactive":
                interactive = msg_data.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    interactive_payload = {
                        "type": "button_reply",
                        "id": interactive["button_reply"]["id"],
                        "title": interactive["button_reply"]["title"],
                    }
                elif interactive.get("type") == "list_reply":
                    interactive_payload = {
                        "type": "list_reply",
                        "id": interactive["list_reply"]["id"],
                        "title": interactive["list_reply"]["title"],
                    }

            return InboundMessage(
                sender_id=phone,
                text=text,
                message_id=msg_id,
                message_type=msg_type if msg_type in ["text", "interactive", "image"] else "unknown",
                interactive_payload=interactive_payload,
                sender_name=sender_name,
                media_id=media_id,
            )

        except (KeyError, IndexError):
            return None

    async def verify_signature(self, body: bytes, headers: Mapping[str, str]) -> bool:
        if settings.ENVIRONMENT == "local":
            return True

        signature = headers.get("X-Hub-Signature-256", "")
        if not signature:
            return False

        expected = "sha256=" + hmac.new(
            self.app_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected)

    def build_verification_response(self, query_params: Mapping[str, str]) -> Any:
        # Responde ao hub.challenge da Meta.
        if query_params.get("hub.verify_token") != self.verify_token:
            return Response(content="Verification failed", status_code=403)
        return Response(content=query_params.get("hub.challenge"), media_type="text/plain")

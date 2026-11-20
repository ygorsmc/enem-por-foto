"""Parsing de payloads reais dos provedores + utilitários de texto."""

import asyncio

import httpx
import pytest
from tenacity import wait_none

from src.channels.markdown import to_whatsapp_markdown
from src.channels.telegram import TelegramChannel
from src.channels.text_utils import chunk_text
from src.channels.whatsapp import WhatsAppChannel


def _wa_payload(msg: dict, contacts: list | None = None) -> dict:
    value = {"messages": [msg]}
    if contacts:
        value["contacts"] = contacts
    return {"entry": [{"changes": [{"value": value}]}]}


class TestWhatsAppParseInbound:
    channel = WhatsAppChannel()

    def test_text_message(self):
        msg = self.channel.parse_inbound(_wa_payload(
            {"from": "5511999999999", "id": "wamid.1", "type": "text", "text": {"body": "/corrigir"}},
            contacts=[{"profile": {"name": "Ana"}}],
        ))
        assert msg is not None
        assert msg.sender_id == "5511999999999"
        assert msg.text == "/corrigir"
        assert msg.message_type == "text"
        assert msg.sender_name == "Ana"

    def test_image_message_carries_media_id_not_bytes(self):
        msg = self.channel.parse_inbound(_wa_payload(
            {"from": "5511999999999", "id": "wamid.2", "type": "image",
             "image": {"id": "MEDIA123", "caption": "minha redação"}},
        ))
        assert msg is not None
        assert msg.message_type == "image"
        assert msg.media_id == "MEDIA123"
        assert msg.text == "minha redação"

    def test_button_reply(self):
        msg = self.channel.parse_inbound(_wa_payload(
            {"from": "5511999999999", "id": "wamid.3", "type": "interactive",
             "interactive": {"type": "button_reply",
                             "button_reply": {"id": "consent_yes", "title": "Aceito ✅"}}},
        ))
        assert msg is not None
        assert msg.message_type == "interactive"
        assert msg.interactive_payload["id"] == "consent_yes"

    def test_status_update_is_ignored(self):
        assert self.channel.parse_inbound(
            {"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}
        ) is None


class TestTelegramParseInbound:
    channel = TelegramChannel()

    def test_text_message(self):
        msg = self.channel.parse_inbound({
            "message": {"chat": {"id": 42}, "message_id": 7,
                        "from": {"first_name": "João", "last_name": "Silva"}, "text": "oi"},
        })
        assert msg is not None
        assert msg.sender_id == "42"
        assert msg.text == "oi"
        assert msg.sender_name == "João Silva"

    def test_photo_takes_highest_resolution(self):
        msg = self.channel.parse_inbound({
            "message": {"chat": {"id": 42}, "message_id": 8, "from": {"first_name": "J"},
                        "photo": [{"file_id": "small"}, {"file_id": "big"}]},
        })
        assert msg is not None
        assert msg.message_type == "image"
        assert msg.media_id == "big"

    def test_callback_query(self):
        msg = self.channel.parse_inbound({
            "callback_query": {"message": {"chat": {"id": 42}, "message_id": 9},
                               "from": {"first_name": "J"}, "data": "confirm_correct"},
        })
        assert msg is not None
        assert msg.message_type == "interactive"
        assert msg.interactive_payload["id"] == "confirm_correct"


class TestChunkText:
    def test_short_text_single_chunk(self):
        assert chunk_text("oi", 100) == ["oi"]

    def test_prefers_paragraph_boundary(self):
        text = ("a" * 50) + "\n\n" + ("b" * 60)
        chunks = chunk_text(text, 80)
        assert chunks[0] == "a" * 50
        assert chunks[1] == "b" * 60

    def test_never_exceeds_max(self):
        chunks = chunk_text("palavra " * 2000, 4000)
        assert all(len(c) <= 4000 for c in chunks)


class TestWhatsAppMarkdown:
    def test_commonmark_bold_becomes_wa_bold(self):
        assert to_whatsapp_markdown("**forte**") == "*forte*"

    def test_wa_dialect_untouched(self):
        assert to_whatsapp_markdown("*forte* e _leve_") == "*forte* e _leve_"

    def test_heading_becomes_bold_line(self):
        assert to_whatsapp_markdown("### Título") == "*Título*"

    def test_table_becomes_monospace(self):
        table = "| a | b |\n|---|---|\n| 1 | 2 |"
        out = to_whatsapp_markdown(table)
        assert out.startswith("```")
        assert "|---|" not in out


class TestTelegramSendRetry:
    """Falha de conexão (TLS caindo) repete; timeout de leitura não (o pedido pode ter chegado)."""

    def _patch(self, monkeypatch, erros: list[Exception]) -> list[str]:
        chamadas: list[str] = []

        async def fake_post(self_client, url, json, timeout):
            chamadas.append(url)
            if erros:
                raise erros.pop(0)
            return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        # Sem espera entre tentativas no teste.
        monkeypatch.setattr(
            TelegramChannel, "_send_request", TelegramChannel._send_request.retry_with(wait=wait_none())
        )
        return chamadas

    def test_conexao_caida_repete_e_entrega(self, monkeypatch):
        chamadas = self._patch(monkeypatch, [httpx.ConnectError(""), httpx.ConnectError("")])
        out = asyncio.run(TelegramChannel().send_buttons("1", "O que fazemos?", [{"id": "a", "title": "A"}]))
        assert out == {"ok": True} and len(chamadas) == 3

    def test_timeout_de_leitura_nao_repete(self, monkeypatch):
        chamadas = self._patch(monkeypatch, [httpx.ReadTimeout("")])
        with pytest.raises(httpx.ReadTimeout):
            asyncio.run(TelegramChannel().send_text("1", "oi"))
        assert len(chamadas) == 1


class TestWhatsAppTyping:
    """'Digitando...' no WhatsApp: status de leitura atrelado à mensagem recebida (não é mensagem cobrada)."""

    def test_typing_marks_read_with_indicator(self, monkeypatch):
        sent = []

        async def fake_send(self, message):
            sent.append(message)
            return {}

        monkeypatch.setattr(WhatsAppChannel, "_send_request", fake_send)
        asyncio.run(WhatsAppChannel().send_typing("5511999999999", "wamid.9"))
        assert sent == [{
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": "wamid.9",
            "typing_indicator": {"type": "text"},
        }]

    def test_typing_without_message_id_is_noop(self, monkeypatch):
        async def fail(self, message):
            raise AssertionError("não deveria chamar a API")

        monkeypatch.setattr(WhatsAppChannel, "_send_request", fail)
        asyncio.run(WhatsAppChannel().send_typing("5511999999999"))

    def test_typing_failure_never_breaks_the_flow(self, monkeypatch):
        async def boom(self, message):
            raise RuntimeError("400")

        monkeypatch.setattr(WhatsAppChannel, "_send_request", boom)
        asyncio.run(WhatsAppChannel().send_typing("5511999999999", "wamid.9"))  # não levanta

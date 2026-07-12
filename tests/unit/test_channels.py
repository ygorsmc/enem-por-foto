"""Parsing de payloads reais dos provedores + utilitários de texto."""

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

"""Testes puros do despacho de job (src/tasks.py): serialização round-trip e o
backend "memory" (default) disparando process_job. O backend "azure" faz I/O de
rede real — não pertence a tests/unit/ (ver AGENTS.md §Testes)."""

import asyncio

import src.tasks as tasks
from src.channels.interfaces import InboundMessage
from src.tasks import deserialize_job, process_job, serialize_job, submit_job
from tests.unit.conftest import button_msg, image_msg, text_msg

run = asyncio.run


class TestJobSerialization:
    def test_round_trip_text(self):
        msg = text_msg("hello world", msg_id="abc")
        channel_name, restored = deserialize_job(serialize_job("telegram", msg))
        assert channel_name == "telegram"
        assert restored == msg

    def test_round_trip_image_keeps_media_id(self):
        msg = image_msg(media_id="photo-42")
        _, restored = deserialize_job(serialize_job("whatsapp", msg))
        assert restored.media_id == "photo-42"
        assert restored.message_type == "image"

    def test_round_trip_button_keeps_payload(self):
        msg = button_msg("confirm_correct")
        _, restored = deserialize_job(serialize_job("telegram", msg))
        assert restored.interactive_payload == {
            "type": "button_reply",
            "id": "confirm_correct",
            "title": "confirm_correct",
        }

    def test_restored_is_inbound_message(self):
        _, restored = deserialize_job(serialize_job("telegram", text_msg("x")))
        assert isinstance(restored, InboundMessage)


class TestProcessJob:
    def test_swallows_flow_exceptions(self, monkeypatch):
        async def boom(channel, msg):
            raise RuntimeError("flow blew up")

        monkeypatch.setattr(tasks, "handle_message", boom)
        monkeypatch.setattr(tasks, "get_channel", lambda name: object())
        # Nenhuma exceção pode escapar — o worker/loop tem que continuar de pé.
        run(process_job("telegram", text_msg("x")))


class TestSubmitJobMemoryBackend:
    def test_dispatches_to_process_job(self, monkeypatch):
        seen: list[tuple[str, str]] = []

        async def fake_process(channel_name, msg):
            seen.append((channel_name, msg.text))

        monkeypatch.setattr(tasks.settings, "QUEUE_BACKEND", "memory")
        monkeypatch.setattr(tasks, "process_job", fake_process)

        async def drive():
            await submit_job("telegram", text_msg("route me"))
            # Backend memory é fire-and-forget: deixa a task agendada rodar.
            await asyncio.sleep(0)

        run(drive())
        assert seen == [("telegram", "route me")]

    def test_does_not_enqueue_azure_when_memory(self, monkeypatch):
        called = False

        async def fake_enqueue(channel_name, msg):
            nonlocal called
            called = True

        async def fake_process(channel_name, msg):
            return None

        monkeypatch.setattr(tasks.settings, "QUEUE_BACKEND", "memory")
        monkeypatch.setattr(tasks, "_enqueue_azure", fake_enqueue)
        monkeypatch.setattr(tasks, "process_job", fake_process)

        async def drive():
            await submit_job("telegram", text_msg("x"))
            await asyncio.sleep(0)

        run(drive())
        assert called is False

"""Testes puros do despacho de job (src/tasks.py): serialização round-trip, o
backend "memory" (default) disparando process_job e o worker da fila do backend
"azure" contra uma fila FALSA em memória (sem rede: o SDK real não é usado)."""

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

    def test_log_mascara_token_e_diz_onde(self, monkeypatch):
        async def boom(channel, msg):
            raise RuntimeError("400 for url 'https://api.telegram.org/bot123456:AAH-x_y9/sendMessage'")

        logged: dict = {}

        class _Log:
            def error(self, event, **kw):
                logged.update(kw, event=event)

        monkeypatch.setattr(tasks, "handle_message", boom)
        monkeypatch.setattr(tasks, "get_channel", lambda name: object())
        monkeypatch.setattr(tasks, "logger", _Log())
        run(process_job("telegram", text_msg("x")))
        assert "123456:AAH" not in logged["error"] and "bot<token>/sendMessage" in logged["error"]
        assert logged["error_type"] == "RuntimeError"
        assert logged["where"].startswith("tasks.py:")
        assert "exc_info" not in logged


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


class _FakeQueueMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeQueueClient:
    """Fila em memória com a parte da interface do QueueClient (aio) que o worker usa."""

    def __init__(self, payloads: list[str]):
        self.pending = [_FakeQueueMessage(p) for p in payloads]
        self.deleted: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def create_queue(self):
        return None

    def receive_messages(self, *, max_messages=None, visibility_timeout=None, messages_per_page=None):
        pending = self.pending

        async def page():
            if pending:
                yield pending.pop(0)

        return page()

    async def delete_message(self, message):
        self.deleted.append(message.content)


def _job(sender: str, text: str) -> str:
    msg = InboundMessage(sender_id=sender, text=text, message_id=f"{sender}-{text}", message_type="text")
    return serialize_job("telegram", msg)


async def _run_worker_until(fake: _FakeQueueClient, done, timeout: float = 2.0) -> None:
    worker = asyncio.create_task(tasks.worker_loop())
    try:
        async def wait_done():
            while not done():
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_done(), timeout)
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


class TestAzureQueueWorker:
    """O worker processa várias mensagens ao mesmo tempo: a correção de um aluno (~1 min de espera de rede)
    não pode travar a conversa dos outros — o bug visto com duas contas no Telegram (2026-11-18)."""

    def _setup(self, monkeypatch, payloads, concurrency=8):
        fake = _FakeQueueClient(payloads)
        monkeypatch.setattr(tasks, "_queue_client", lambda: fake)
        monkeypatch.setattr(tasks.settings, "QUEUE_POLL_INTERVAL", 0)
        monkeypatch.setattr(tasks.settings, "QUEUE_MAX_CONCURRENCY", concurrency)
        return fake

    def test_dois_alunos_processados_em_paralelo(self, monkeypatch):
        fake = self._setup(monkeypatch, [_job("aluno1", "corrige"), _job("aluno2", "oi")])

        async def drive():
            started: list[str] = []
            both_started = asyncio.Event()

            async def fake_process(channel_name, msg):
                started.append(msg.sender_id)
                if len(started) == 2:
                    both_started.set()
                # Com um worker sequencial, o 1º job esperaria aqui para sempre pelo 2º.
                await asyncio.wait_for(both_started.wait(), timeout=1)

            monkeypatch.setattr(tasks, "process_job", fake_process)
            await _run_worker_until(fake, lambda: len(fake.deleted) == 2)
            return started

        started = run(drive())
        assert sorted(started) == ["aluno1", "aluno2"]
        assert len(fake.deleted) == 2

    def test_respeita_o_teto_de_concorrencia(self, monkeypatch):
        fake = self._setup(monkeypatch, [_job(f"aluno{i}", "x") for i in range(5)], concurrency=2)

        async def drive():
            in_flight = 0
            peak = 0

            async def fake_process(channel_name, msg):
                nonlocal in_flight, peak
                in_flight += 1
                peak = max(peak, in_flight)
                await asyncio.sleep(0.05)
                in_flight -= 1

            monkeypatch.setattr(tasks, "process_job", fake_process)
            await _run_worker_until(fake, lambda: len(fake.deleted) == 5)
            return peak

        assert run(drive()) == 2
        assert len(fake.deleted) == 5

    def test_payload_malformado_e_descartado_sem_parar_o_worker(self, monkeypatch):
        fake = self._setup(monkeypatch, ["{isto não é json", _job("aluno1", "ok")])

        async def drive():
            seen: list[str] = []

            async def fake_process(channel_name, msg):
                seen.append(msg.text)

            monkeypatch.setattr(tasks, "process_job", fake_process)
            await _run_worker_until(fake, lambda: len(fake.deleted) == 2)
            return seen

        assert run(drive()) == ["ok"]
        assert fake.deleted[0] == "{isto não é json"

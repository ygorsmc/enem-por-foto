"""Despacho de job: desacopla RECEBER uma mensagem (webhook, precisa responder
<200ms) de PROCESSÁ-la (download de mídia + OCR + LLM, ~90-100s). Dois backends
plugáveis, escolhidos por QUEUE_BACKEND — mesmo contrato, durabilidade diferente:

  - "memory" (default): asyncio.create_task no mesmo processo. O modo mono-
    contêiner clássico (minReplicas=1) — dev, simulador, testes, e um deploy de
    produção perfeitamente válido. A task em voo vive só em RAM.

  - "azure": enfileira numa Azure Storage Queue; um worker (iniciado no lifespan
    da app) drena a fila. É isso que permite o Azure Container Apps escalar pra
    ZERO réplicas com um KEDA azure-queue scaler: a fila DURÁVEL mantém o
    trabalho pendente visível ao autoscaler (uma task em memória não é), então
    o contêiner só roda — e só é cobrado — enquanto há redação a processar.
    Exige Redis EXTERNO (Upstash): o Redis embutido morre quando a réplica
    escala pra zero, levando o estado da conversa junto. Ver deploy/README.md.

Invariante preservado nos dois casos: o handler do webhook NUNCA processa — só
chama submit_job() e retorna 200. process_job() é onde o trabalho pesado roda,
e engole toda exceção pra uma mensagem ruim não derrubar o worker.
"""

import asyncio
import json
from dataclasses import asdict

import structlog

from src.channels.factory import get_channel
from src.channels.interfaces import InboundMessage
from src.config import settings
from src.flow.handlers import handle_message

logger = structlog.get_logger(__name__)

# Referências fortes: sem isso o GC pode matar uma task em voo (backend memory).
_background_tasks: set[asyncio.Task] = set()


def serialize_job(channel_name: str, msg: InboundMessage) -> str:
    """Payload JSON colocado na fila (backend azure). Dataclass simples → dict."""
    return json.dumps({"channel": channel_name, "msg": asdict(msg)}, ensure_ascii=False)


def deserialize_job(payload: str) -> tuple[str, InboundMessage]:
    data = json.loads(payload)
    return data["channel"], InboundMessage(**data["msg"])


async def process_job(channel_name: str, msg: InboundMessage) -> None:
    """Resolve o canal e roda o fluxo. Nenhuma exceção escapa (fluxo isolado):
    uma mensagem que falha não pode derrubar o worker nem reentregar-e-cobrar-em-dobro."""
    try:
        channel = get_channel(channel_name)
        await handle_message(channel, msg)
    except Exception as e:
        logger.error(
            "flow_unhandled_exception",
            channel=channel_name,
            sender=msg.sender_id,
            error=str(e)[:300],
        )


async def submit_job(channel_name: str, msg: InboundMessage) -> None:
    """Chamado pelo handler do webhook. Retorna rápido (fire-and-forget / enfileira)."""
    if settings.QUEUE_BACKEND == "azure":
        await _enqueue_azure(channel_name, msg)
        return
    task = asyncio.create_task(process_job(channel_name, msg))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# ── Backend Azure Storage Queue ─────────────────────────────────────────────
# azure-storage-queue é importado tardiamente: o backend memory (dev/testes)
# nunca precisa dele instalado, e importar este módulo continua barato.


def _queue_client():
    from azure.storage.queue import TextBase64DecodePolicy, TextBase64EncodePolicy
    from azure.storage.queue.aio import QueueClient

    return QueueClient.from_connection_string(
        settings.AZURE_STORAGE_CONNECTION_STRING,
        settings.ESSAY_QUEUE_NAME,
        # Base64 mantém UTF-8 arbitrário seguro no transporte XML da fila e é o
        # que o azure-queue scaler do KEDA espera por padrão.
        message_encode_policy=TextBase64EncodePolicy(),
        message_decode_policy=TextBase64DecodePolicy(),
    )


async def _enqueue_azure(channel_name: str, msg: InboundMessage) -> None:
    async with _queue_client() as client:
        await client.send_message(serialize_job(channel_name, msg))


async def worker_loop() -> None:
    """Drena a Azure Storage Queue. Iniciado no lifespan da app quando
    QUEUE_BACKEND == "azure". Roda até ser cancelado (shutdown da app)."""
    logger.info("queue_worker_started", queue=settings.ESSAY_QUEUE_NAME)
    async with _queue_client() as client:
        try:
            await client.create_queue()  # no-op se já existir
        except Exception:
            pass
        while True:
            try:
                received_any = False
                async for message in client.receive_messages(
                    messages_per_page=1,
                    visibility_timeout=settings.QUEUE_VISIBILITY_TIMEOUT,
                ):
                    received_any = True
                    try:
                        channel_name, msg = deserialize_job(message.content)
                        await process_job(channel_name, msg)
                    except Exception as e:
                        # Payload malformado: loga e descarta (delete abaixo) — reentregar
                        # uma mensagem que nem dá pra parsear ficaria em loop pra sempre.
                        logger.error("queue_job_failed", error=str(e)[:300])
                    # Apaga só APÓS o job ter RODADO. process_job engole erros do fluxo,
                    # então uma mensagem que executou (mesmo terminando numa falha
                    # tratada) não pode reentregar e cobrar OCR/LLM em dobro. Só um crash
                    # bruto antes deste delete reentrega (após o visibility_timeout) —
                    # raro e aceito num bot de escala pessoal.
                    await client.delete_message(message)
                if not received_any:
                    await asyncio.sleep(settings.QUEUE_POLL_INTERVAL)
            except asyncio.CancelledError:
                logger.info("queue_worker_stopped")
                raise
            except Exception as e:
                logger.error("queue_worker_error", error=str(e)[:300])
                await asyncio.sleep(settings.QUEUE_POLL_INTERVAL)

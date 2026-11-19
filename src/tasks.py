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
import re
import traceback
from dataclasses import asdict

import structlog

from src.channels.factory import get_channel
from src.channels.interfaces import InboundMessage
from src.config import settings
from src.flow.handlers import handle_message

logger = structlog.get_logger(__name__)

# O str() de um HTTPStatusError do httpx traz a URL, e a do Telegram contém o token do bot.
_TELEGRAM_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")

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
        # Sem exc_info: o traceback do console imprime as variáveis locais (URL com o token do bot,
        # chaves de API). Tipo + onde (frames de src/) bastam para diagnosticar.
        frames = [f for f in traceback.extract_tb(e.__traceback__) if "/src/" in f.filename]
        logger.error(
            "flow_unhandled_exception",
            channel=channel_name,
            sender=msg.sender_id,
            error_type=type(e).__name__,  # erros de conexão do httpx chegam com str(e) vazio
            where=" > ".join(f"{f.filename.split('/src/')[-1]}:{f.lineno}" for f in frames[-3:]),
            error=_TELEGRAM_TOKEN_RE.sub("bot<token>", str(e))[:300],
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


async def _receive_one(client):
    """Próxima mensagem da fila (invisível aos outros por QUEUE_VISIBILITY_TIMEOUT) ou None se vazia."""
    async for message in client.receive_messages(
        max_messages=1, visibility_timeout=settings.QUEUE_VISIBILITY_TIMEOUT
    ):
        return message
    return None


async def _run_queued_job(client, message, slots: asyncio.Semaphore) -> None:
    """Roda UMA mensagem da fila e a apaga depois. Sempre devolve a vaga do worker."""
    try:
        try:
            channel_name, msg = deserialize_job(message.content)
        except Exception as e:
            # Payload malformado: loga e descarta (delete abaixo) — reentregar uma
            # mensagem que nem dá pra parsear ficaria em loop pra sempre.
            logger.error("queue_job_failed", error=str(e)[:300])
        else:
            await process_job(channel_name, msg)
        # Apaga só APÓS o job ter RODADO. process_job engole erros do fluxo, então uma
        # mensagem que executou (mesmo terminando numa falha tratada) não pode reentregar
        # e cobrar OCR/LLM em dobro. Só um crash bruto antes deste delete reentrega (após
        # o visibility_timeout) — raro e aceito num bot de escala pessoal.
        await client.delete_message(message)
    except Exception as e:
        logger.error("queue_delete_failed", error_type=type(e).__name__, error=str(e)[:300])
    finally:
        slots.release()


async def worker_loop() -> None:
    """Drena a Azure Storage Queue. Iniciado no lifespan da app quando
    QUEUE_BACKEND == "azure". Roda até ser cancelado (shutdown da app).

    Até QUEUE_MAX_CONCURRENCY mensagens em paralelo, cada uma numa task — o mesmo
    comportamento do backend "memory". Toda mensagem do aluno (texto, botão, foto)
    passa pela fila; processando uma por vez, a correção de um aluno (~50-90 s,
    quase tudo espera de rede: OCR, Jev, LLM) travava a conversa de todos os outros.
    """
    slots = asyncio.Semaphore(settings.QUEUE_MAX_CONCURRENCY)
    logger.info(
        "queue_worker_started", queue=settings.ESSAY_QUEUE_NAME, concurrency=settings.QUEUE_MAX_CONCURRENCY
    )
    async with _queue_client() as client:
        try:
            await client.create_queue()  # no-op se já existir
        except Exception:
            pass
        while True:
            holding = False  # esta volta do laço segura uma vaga ainda não entregue a uma task?
            try:
                await slots.acquire()  # espera vaga: no máximo QUEUE_MAX_CONCURRENCY jobs em voo
                holding = True
                message = await _receive_one(client)
                if message is None:
                    slots.release()
                    holding = False
                    await asyncio.sleep(settings.QUEUE_POLL_INTERVAL)
                    continue
                task = asyncio.create_task(_run_queued_job(client, message, slots))
                holding = False  # a vaga agora é da task (devolvida no finally dela)
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)
            except asyncio.CancelledError:
                if holding:
                    slots.release()
                logger.info("queue_worker_stopped")
                raise
            except Exception as e:
                if holding:
                    slots.release()
                logger.error("queue_worker_error", error=str(e)[:300])
                await asyncio.sleep(settings.QUEUE_POLL_INTERVAL)

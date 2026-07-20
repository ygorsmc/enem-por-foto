"""Borda HTTP (mono-serviço): recebe os webhooks do WhatsApp/Telegram, valida,
responde 200 em <200ms e despacha o processamento para uma task asyncio.

Invariantes herdados do projeto pai:
  - O handler do webhook NUNCA chama LLM, OCR nem baixa mídia — só valida,
    parseia e agenda a task (SLA de 200ms da Meta).
  - Meta/Telegram nunca recebem status != 2xx nas rotas de webhook (um não-2xx
    dispara flood de retries) — falhas degradam para 200.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request, Response

from src.channels.factory import get_channel
from src.config import settings
from src.redis_client import is_duplicate_message
from src.tasks import submit_job, worker_loop

logger = structlog.get_logger(__name__)

_VALID_CHANNELS = ("whatsapp", "telegram")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """No backend "azure", roda o worker que drena a fila junto com o processo
    do webhook (mesmo contêiner: HTTP recebe + worker drena). O KEDA azure-queue
    scaler mantém a réplica viva enquanto a fila tem mensagem e escala pra zero
    quando ociosa. O backend "memory" não tem worker (tasks rodam em processo),
    então isso é um no-op nesse caso."""
    worker: asyncio.Task | None = None
    if settings.QUEUE_BACKEND == "azure":
        worker = asyncio.create_task(worker_loop())
    yield
    if worker is not None:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Corretor ENEM", docs_url=None, redoc_url=None, lifespan=lifespan)


def _setup_logging() -> None:
    logging.basicConfig(level=settings.LOG_LEVEL, format="%(message)s")
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        ),
    )


_setup_logging()


def _resolve_channel(channel_name: str):
    if channel_name not in _VALID_CHANNELS:
        raise HTTPException(status_code=404)
    return get_channel(channel_name)


@app.get("/v1/webhook/{channel_name}")
async def verify_webhook(channel_name: str, request: Request):
    channel = _resolve_channel(channel_name)
    return channel.build_verification_response(dict(request.query_params))


@app.post("/v1/webhook/{channel_name}")
async def receive_webhook(channel_name: str, request: Request):
    channel = _resolve_channel(channel_name)

    body = await request.body()
    if not await channel.verify_signature(body, request.headers):
        logger.warning("webhook_signature_failed", channel=channel_name)
        # 200 mesmo assim: não dar oráculo de assinatura nem provocar retries.
        return Response(status_code=200)

    msg = channel.parse_inbound(await request.json())
    if msg is None or msg.message_type == "unknown":
        return Response(status_code=200)

    # Idempotência: Meta/Telegram reenviam o mesmo update em timeout/restart.
    if await is_duplicate_message(f"{channel_name}:{msg.message_id}"):
        logger.info("webhook_duplicate_dropped", channel=channel_name, message_id=msg.message_id)
        return Response(status_code=200)

    # Despacha para o backend de processamento (task em processo ou Azure Queue)
    # e responde na hora — o handler nunca pode rodar OCR/LLM (SLA de 200ms da Meta).
    await submit_job(channel_name, msg)

    return Response(status_code=200)


@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    if request.url.path.startswith("/v1/webhook/"):
        logger.error("webhook_unhandled_exception", path=request.url.path, error=str(exc)[:300])
        return Response(status_code=200)
    logger.error("unhandled_exception", path=request.url.path, error=str(exc)[:300])
    return Response(status_code=500)


@app.get("/health")
async def health_check():
    return {"status": "ok"}

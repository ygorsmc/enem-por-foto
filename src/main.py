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

import structlog
from fastapi import FastAPI, HTTPException, Request, Response

from src.channels.factory import get_channel
from src.config import settings
from src.flow.handlers import handle_message
from src.redis_client import is_duplicate_message

logger = structlog.get_logger(__name__)

app = FastAPI(title="Corretor ENEM", docs_url=None, redoc_url=None)

# Referências fortes: sem isso o GC pode matar uma task em andamento.
_background_tasks: set[asyncio.Task] = set()

_VALID_CHANNELS = ("whatsapp", "telegram")


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


async def _process(channel, msg) -> None:
    """Corpo da task de background — nenhuma exceção escapa (fluxo isolado)."""
    try:
        await handle_message(channel, msg)
    except Exception as e:
        logger.error(
            "flow_unhandled_exception",
            channel=channel.channel_name,
            sender=msg.sender_id,
            error=str(e)[:300],
        )


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

    task = asyncio.create_task(_process(channel, msg))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

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

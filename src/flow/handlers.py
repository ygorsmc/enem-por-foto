"""Máquina de estados da conversa: consentimento → tema → motivadores → foto (ou
texto digitado) → confirmação (com edição manual opcional do texto) → correção.

Roda SEMPRE na task de background (nunca no handler HTTP do webhook): é aqui
que acontecem download de mídia, OCR e LLM. Regras herdadas do pai:
  - OCR só na redação — tema e motivadores são texto digitado (foto é recusada
    com orientação, para não queimar Mistral à toa).
  - A foto é descartada após o OCR (só o texto vive no estado, com TTL).
  - Rate-limit é consumido na CORREÇÃO (o passeio pelo fluxo é grátis); falha
    técnica na correção devolve o crédito.
"""

import hashlib
import time

import structlog

from src import messages as m
from src.channels.interfaces import IMessagingChannel, InboundMessage
from src.config import settings
from src.correction.corrector import correct_essay
from src.correction.ocr import ocr_image
from src.flow.states import (
    FlowData,
    FlowState,
    accepted_consent_version,
    clear_flow,
    grant_consent,
    load_flow,
    revoke_consent,
    save_flow,
)
from src.rate_limit import (
    check_and_increment,
    consume_photo_read,
    daily_count_key,
    daily_photo_limit,
    has_quota,
)
from src.redis_client import get_redis

logger = structlog.get_logger(__name__)

MIN_THEME_CHARS = 10
# Quantas palavras "a conferir" aparecem no preview (as piores primeiro). Acima
# desse total, a leitura é considerada difícil no geral e a mensagem muda de
# "confira estas palavras" para "releia o texto inteiro" (ver calibração em ocr.py).
FLAGGED_WORDS_SHOWN = 8
# Teto do que fica guardado no estado (entre fotos); o mostrado é um subconjunto.
MAX_FLAGGED_WORDS_STORED = 30


def _merge_flagged(existing: list[str], new: list[str]) -> list[str]:
    """Acumula as palavras de baixa confiança entre fotos, sem duplicar, com teto."""
    seen = {w.lower() for w in existing}
    merged = list(existing)
    for w in new:
        if w.lower() not in seen:
            seen.add(w.lower())
            merged.append(w)
    return merged[:MAX_FLAGGED_WORDS_STORED]


def _consent_terms() -> str:
    """Corpo do termo para o modo e o provedor em uso: nomeia os serviços por onde a redação passa."""
    hibrido = settings.CORRECTION_MODE == "hibrido"
    template = m.CONSENT_TERMS_HIBRIDO if hibrido else m.CONSENT_TERMS_LLM
    provider = settings.CORRECTION_PROVIDER
    return template.format(
        llm=m.LLM_PROVIDER_LABELS.get(provider, f"*{provider}*"),
        minutos=settings.FLOW_TTL_SECONDS // 60,
    )


def _consent_version() -> str:
    """Versão do termo = hash do corpo mostrado ao aluno. Qualquer mudança no texto (outro provedor, outro modo,
    outro prazo de guarda, nova redação) muda a versão, e quem aceitou a anterior vê o termo de novo."""
    return hashlib.sha256(_consent_terms().encode("utf-8")).hexdigest()[:12]


def _consent_text(updated: bool = False) -> str:
    """Primeiro contato: saudação + termo. Aceite de versão anterior: aviso de que o termo mudou + termo."""
    return (m.CONSENT_INTRO_UPDATED if updated else m.CONSENT_INTRO) + _consent_terms()


def _correction_footer() -> str:
    """No modo híbrido a nota vem do modelo de machine learning; no modo llm, do próprio LLM."""
    return m.CORRECTION_FOOTER_HIBRIDO if settings.CORRECTION_MODE == "hibrido" else m.CORRECTION_FOOTER


def _button_id(msg: InboundMessage) -> str | None:
    if msg.message_type == "interactive" and msg.interactive_payload:
        return msg.interactive_payload.get("id")
    return None


def _command(msg: InboundMessage) -> str | None:
    """Comando normalizado ('/corrigir', '/cancelar', '/ajuda') ou None."""
    text = (msg.text or "").strip().lower()
    if not text.startswith("/"):
        return None
    return text.split()[0]


async def handle_message(channel: IMessagingChannel, msg: InboundMessage) -> None:
    """Ponto de entrada único do fluxo (chamado pelo webhook via task)."""
    ch = channel.channel_name
    sender = msg.sender_id
    btn = _button_id(msg)

    # ── Portão de consentimento (LGPD — nada é processado antes do aceite) ──
    # O aceite vale para a versão do termo que o aluno viu: texto novo → aceite de novo.
    version = _consent_version()
    accepted = await accepted_consent_version(ch, sender)
    if accepted != version:
        if btn == "consent_yes":
            await grant_consent(ch, sender, version)
            # Já começa o fluxo: as boas-vindas e o pedido do tema vão numa mensagem só.
            await save_flow(ch, sender, FlowData(state=FlowState.AWAITING_THEME))
            await channel.send_text(sender, m.WELCOME_START)
        elif btn == "consent_no":
            await revoke_consent(ch, sender)  # recusou a versão nova: o aceite antigo também deixa de valer
            await clear_flow(ch, sender)
            await channel.send_text(sender, m.CONSENT_DECLINED)
        else:
            await channel.send_buttons(
                sender, _consent_text(updated=accepted is not None), [m.CONSENT_BTN_YES, m.CONSENT_BTN_NO]
            )
        return

    # ── Comandos globais (valem em qualquer estado) ──────────────────────────
    command = _command(msg)
    if command == "/cancelar":
        await clear_flow(ch, sender)
        await channel.send_text(sender, m.CANCELLED)
        return
    if command == "/corrigir" or btn == "start_correction":
        await _start_correction(channel, sender)
        return
    if command == "/ajuda":
        await channel.send_buttons(sender, m.HELP_MENU, [m.BTN_START])
        return

    flow = await load_flow(ch, sender)

    # ── IDLE (sem fluxo ativo) ───────────────────────────────────────────────
    if flow is None:
        if msg.message_type == "image":
            await channel.send_buttons(sender, m.PHOTO_UNEXPECTED, [m.BTN_START])
        else:
            await channel.send_buttons(sender, m.HELP_MENU, [m.BTN_START])
        return

    state = FlowState(flow.state)
    if state == FlowState.AWAITING_THEME:
        await _handle_awaiting_theme(channel, sender, flow, msg)
    elif state == FlowState.AWAITING_MOTIVATORS:
        await _handle_awaiting_motivators(channel, sender, flow, msg, btn)
    elif state == FlowState.AWAITING_ESSAY_PHOTO:
        await _handle_awaiting_photo(channel, sender, flow, msg)
    elif state == FlowState.CONFIRMING:
        await _handle_confirming(channel, sender, flow, msg, btn)
    elif state == FlowState.EDITING_TEXT:
        await _handle_editing_text(channel, sender, flow, msg, btn)


async def _start_correction(channel: IMessagingChannel, sender: str) -> None:
    """(Re)começa o fluxo: zera qualquer estado anterior e pede o tema."""
    flow = FlowData(state=FlowState.AWAITING_THEME)
    await save_flow(channel.channel_name, sender, flow)
    await channel.send_text(sender, m.ASK_THEME)


async def _handle_awaiting_theme(
    channel: IMessagingChannel, sender: str, flow: FlowData, msg: InboundMessage
) -> None:
    if msg.message_type == "image":
        await channel.send_text(sender, m.THEME_MUST_BE_TEXT)
        return
    theme = (msg.text or "").strip()
    if len(theme) < MIN_THEME_CHARS:
        await channel.send_text(sender, m.THEME_TOO_SHORT)
        return

    flow.theme = theme
    flow.state = FlowState.AWAITING_MOTIVATORS
    await save_flow(channel.channel_name, sender, flow)
    await channel.send_buttons(sender, m.ASK_MOTIVATORS, [m.BTN_SKIP_MOTIVATORS])


async def _handle_awaiting_motivators(
    channel: IMessagingChannel, sender: str, flow: FlowData, msg: InboundMessage, btn: str | None
) -> None:
    if btn in ("skip_motivators", "done_motivators"):
        flow.state = FlowState.AWAITING_ESSAY_PHOTO
        await save_flow(channel.channel_name, sender, flow)
        await channel.send_text(sender, m.ASK_ESSAY_PHOTO)
        return
    if msg.message_type == "image":
        await channel.send_buttons(sender, m.MOTIVATORS_MUST_BE_TEXT, [m.BTN_SKIP_MOTIVATORS])
        return

    text = (msg.text or "").strip()
    if text:
        flow.motivators.append(text)
        await save_flow(channel.channel_name, sender, flow)
    await channel.send_buttons(sender, m.MOTIVATORS_RECEIVED, [m.BTN_DONE_MOTIVATORS])


async def _handle_awaiting_photo(
    channel: IMessagingChannel, sender: str, flow: FlowData, msg: InboundMessage
) -> None:
    if msg.message_type == "image" and msg.media_id:
        await _process_essay_photo(channel, sender, flow, msg.media_id, msg.message_id)
        return
    text = (msg.text or "").strip()
    if msg.message_type == "text" and len(text) >= settings.MIN_ESSAY_CHARS:
        await _accept_typed_essay(channel, sender, flow, text)
        return
    await channel.send_text(sender, m.ESSAY_AWAITING_PHOTO_REMINDER)


async def _accept_typed_essay(channel: IMessagingChannel, sender: str, flow: FlowData, text: str) -> None:
    """Redação digitada ou colada no lugar da foto: sem OCR (e sem gastar leitura de foto). Segue o mesmo caminho
    da edição manual: eco do texto e confirmação antes de corrigir."""
    ch = channel.channel_name
    if not await has_quota(ch, sender):
        await channel.send_text(sender, m.RATE_LIMITED.format(limit=settings.ESSAY_DAILY_LIMIT))
        return
    flow.essay_parts = [text]
    flow.flagged_words = []
    flow.state = FlowState.CONFIRMING
    await save_flow(ch, sender, flow)
    logger.info("essay_typed_received", channel=ch, chars=len(text))
    preview = flow.essay_text[: settings.OCR_PREVIEW_MAX_CHARS]
    await channel.send_buttons(
        sender,
        m.TYPED_TEXT_PREVIEW.format(essay_text=preview),
        [m.BTN_CONFIRM_CORRECT, m.BTN_EDIT_TEXT],
    )


async def _process_essay_photo(
    channel: IMessagingChannel, sender: str, flow: FlowData, media_id: str, message_id: str | None = None
) -> None:
    """Download → OCR → preview + confirmação. A foto (bytes) morre aqui."""
    ch = channel.channel_name

    if not await has_quota(ch, sender):
        await channel.send_text(sender, m.RATE_LIMITED.format(limit=settings.ESSAY_DAILY_LIMIT))
        return
    # Cada foto é uma leitura paga do OCR: conta antes de chamar (inclusive as que falharem).
    if not await consume_photo_read(ch, sender):
        await channel.send_text(
            sender,
            m.PHOTO_LIMIT_REACHED.format(limit=daily_photo_limit(), per_essay=settings.PHOTOS_PER_ESSAY),
        )
        return

    # Só o indicador de "digitando" (não é mensagem; no WhatsApp não entra na cobrança), sem aviso "estou lendo".
    await channel.send_typing(sender, message_id)

    t_task = time.perf_counter()
    try:
        t0 = time.perf_counter()
        image_bytes = await channel.download_media(media_id)
        download_ms = round((time.perf_counter() - t0) * 1000)
        photo_bytes = len(image_bytes)

        t0 = time.perf_counter()
        result = await ocr_image(image_bytes)
        ocr_ms = round((time.perf_counter() - t0) * 1000)
    except Exception as e:
        logger.error("essay_ocr_failed", channel=ch, error=str(e)[:300])
        await channel.send_text(sender, m.ESSAY_OCR_FAILED)
        return
    finally:
        # LGPD: a imagem nunca sobrevive além do OCR.
        image_bytes = None  # noqa: F841

    part = result.text
    # Cada FOTO precisa render texto legível — parte ilegível não entra.
    if len(part.strip()) < settings.MIN_ESSAY_CHARS:
        await channel.send_text(sender, m.ESSAY_OCR_FAILED)
        return

    flow.essay_parts.append(part.strip())
    flow.flagged_words = _merge_flagged(flow.flagged_words, result.low_confidence_words)
    flow.state = FlowState.CONFIRMING
    await save_flow(ch, sender, flow)

    task_ms = round((time.perf_counter() - t_task) * 1000)
    logger.info(
        "essay_photo_timing",
        channel=ch,
        photo_bytes=photo_bytes,
        download_ms=download_ms,
        ocr_ms=ocr_ms,
        overhead_ms=task_ms - download_ms - ocr_ms,
        task_ms=task_ms,
    )

    preview = flow.essay_text[: settings.OCR_PREVIEW_MAX_CHARS]
    preview_msg = m.OCR_PREVIEW.format(ocr_text=preview)
    # Destaca as palavras que o OCR leu com baixa confiança (triagem de atenção —
    # o aluno tem a folha em mãos e decide o que ajustar). Poucas palavras: aponta
    # cada uma. Muitas (letra difícil no geral): pede releitura do texto todo e
    # mostra só as piores, para não despejar uma lista enorme.
    if flow.flagged_words:
        shown = ", ".join(flow.flagged_words[:FLAGGED_WORDS_SHOWN])
        note = (
            m.OCR_FLAGGED_MANY_NOTE
            if len(flow.flagged_words) > FLAGGED_WORDS_SHOWN
            else m.OCR_FLAGGED_NOTE
        )
        preview_msg += note.format(words=shown)
    # Preview e botões numa mensagem só (no WhatsApp, corpo acima de 1024 caracteres vira texto + botões).
    # WhatsApp aceita no máximo 3 botões: "adicionar foto" não vira botão —
    # mandar outra foto direto já acrescenta uma parte (ver _handle_confirming).
    await channel.send_buttons(
        sender,
        preview_msg + "\n\n" + m.CHOOSE_ACTION,
        [m.BTN_CONFIRM_CORRECT, m.BTN_EDIT_TEXT, m.BTN_REDO_PHOTO],
    )


async def _handle_confirming(
    channel: IMessagingChannel, sender: str, flow: FlowData, msg: InboundMessage, btn: str | None
) -> None:
    ch = channel.channel_name

    if btn == "redo_photo":
        flow.essay_parts = []
        flow.flagged_words = []
        flow.state = FlowState.AWAITING_ESSAY_PHOTO
        await save_flow(ch, sender, flow)
        await channel.send_text(sender, m.ASK_ESSAY_PHOTO)
        return

    # "add_photo" cobre botões antigos ainda tocáveis no histórico da conversa.
    if btn == "add_photo" or msg.message_type == "image":
        if len(flow.essay_parts) >= settings.MAX_ESSAY_PHOTOS:
            await channel.send_buttons(
                sender,
                m.MAX_PHOTOS_REACHED.format(max_photos=settings.MAX_ESSAY_PHOTOS),
                [m.BTN_CONFIRM_CORRECT, m.BTN_EDIT_TEXT, m.BTN_REDO_PHOTO],
            )
            return
        if msg.message_type == "image" and msg.media_id:
            # Foto mandada direto na confirmação = mais uma parte da redação.
            await _process_essay_photo(channel, sender, flow, msg.media_id, msg.message_id)
        else:
            flow.state = FlowState.AWAITING_ESSAY_PHOTO
            await save_flow(ch, sender, flow)
            await channel.send_text(sender, m.ASK_NEXT_PHOTO)
        return

    if btn == "edit_text":
        await _start_text_edit(channel, sender, flow)
        return

    if btn == "confirm_correct":
        await _run_correction(channel, sender, flow, msg.message_id)
        return

    await channel.send_text(sender, m.CONFIRMING_REMINDER)


async def _start_text_edit(channel: IMessagingChannel, sender: str, flow: FlowData) -> None:
    """Manda o texto completo numa mensagem própria (fácil de copiar) e passa
    a esperar a versão ajustada pelo aluno (letra difícil → OCR imperfeito)."""
    flow.state = FlowState.EDITING_TEXT
    await save_flow(channel.channel_name, sender, flow)
    await channel.send_text(sender, m.EDIT_TEXT_INSTRUCTIONS)
    await channel.send_text(sender, flow.essay_text)


async def _handle_editing_text(
    channel: IMessagingChannel, sender: str, flow: FlowData, msg: InboundMessage, btn: str | None
) -> None:
    """Recebe o texto ajustado, ecoa de volta e só corrige após confirmação."""
    if btn == "edit_text":
        # Toque repetido no botão enquanto já espera o texto: reenvia a cópia.
        await _start_text_edit(channel, sender, flow)
        return
    if msg.message_type == "image":
        await channel.send_text(sender, m.EDITED_TEXT_MUST_BE_TEXT)
        return

    text = (msg.text or "").strip()
    if len(text) < settings.MIN_ESSAY_CHARS:
        await channel.send_text(sender, m.EDITED_TEXT_TOO_SHORT)
        return

    # O texto ajustado substitui TODAS as partes de OCR (o aluno recebeu e
    # editou a redação já unificada) — e zera o destaque de baixa confiança,
    # já que a leitura foi conferida à mão.
    flow.essay_parts = [text]
    flow.flagged_words = []
    flow.state = FlowState.CONFIRMING
    await save_flow(channel.channel_name, sender, flow)

    preview = flow.essay_text[: settings.OCR_PREVIEW_MAX_CHARS]
    await channel.send_buttons(
        sender,
        m.EDITED_TEXT_PREVIEW.format(essay_text=preview),
        [m.BTN_CONFIRM_CORRECT, m.BTN_EDIT_TEXT],
    )


async def _run_correction(
    channel: IMessagingChannel, sender: str, flow: FlowData, message_id: str | None = None
) -> None:
    """Rate-limit → LLM → feedback. Falha técnica devolve o crédito do dia e
    mantém o estado (o aluno pode tentar de novo sem repetir o fluxo)."""
    ch = channel.channel_name

    if not await check_and_increment(ch, sender):
        await channel.send_text(sender, m.RATE_LIMITED.format(limit=settings.ESSAY_DAILY_LIMIT))
        return

    await channel.send_text(sender, m.CORRECTING)
    await channel.send_typing(sender, message_id)

    t_task = time.perf_counter()
    try:
        t0 = time.perf_counter()
        feedback = await correct_essay(flow.theme, flow.motivators_text, flow.essay_text)
        llm_ms = round((time.perf_counter() - t0) * 1000)
    except Exception as e:
        logger.error("essay_correction_failed", channel=ch, error=str(e)[:300])
        redis = await get_redis()
        await redis.decr(daily_count_key(ch, sender))
        await channel.send_text(sender, m.CORRECTION_FAILED)
        return

    # Estado morre ANTES da entrega: se o envio falhar no meio dos chunks, o
    # aluno recomeça limpo em vez de ficar preso num CONFIRMING fantasma.
    await clear_flow(ch, sender)
    # Sem botão "corrigir outra" (seria mais uma mensagem): o rodapé diz como começar outra correção.
    await channel.send_text(sender, feedback + _correction_footer())
    task_ms = round((time.perf_counter() - t_task) * 1000)
    logger.info(
        "essay_flow_completed",
        channel=ch,
        llm_ms=llm_ms,
        overhead_ms=task_ms - llm_ms,
        task_ms=task_ms,
    )

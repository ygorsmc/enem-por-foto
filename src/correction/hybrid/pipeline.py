"""Correção no modo híbrido: a nota vem do modelo calibrado e o LLM só escreve o feedback.

Passos: texto do OCR normalizado (só para o modelo e o Jev) → Jev (71 perguntas) → features → modelo (níveis
C1..C5, soma = total) → portão de zero / avisos → checklist (pistas) → LLM com as notas FIXAS no bloco
`HYBRID_GRADES_BLOCK` (ou `HYBRID_ZERO_BLOCK`). O LLM recebe a transcrição como o aluno a confirmou, igual ao
modo `llm`. Ver `_local/RELATORIO_JEV.md` §2 para a origem de cada passo.
"""

import asyncio
import re
import time

import structlog

from src.correction.factory import get_corrector
from src.correction.hybrid import artifacts
from src.correction.hybrid.features import all_features, normalize_ocr_text, word_count
from src.correction.hybrid.jev import ask_jev
from src.correction.hybrid.model import predict_levels
from src.correction.hybrid.scoring import COMPS, checklist_hits, evaluate_gate, pistas_text
from src.prompts import HYBRID_GRADES_BLOCK, HYBRID_ZERO_BLOCK

logger = structlog.get_logger(__name__)

# O formato do WhatsApp/Telegram usa *um* asterisco para negrito; alguns modelos insistem em **dois**.
_NEGRITO_DUPLO = re.compile(r"\*\*(.+?)\*\*")
# O prompt proíbe mencionar as pistas; isto só registra se escapar (não altera o texto).
_VAZAMENTO = re.compile(r"pista|leitura automática|triagem automática", re.I)


async def grade(tema: str, essay_text: str) -> tuple[list[int], str | None, str]:
    """→ (níveis C1..C5, motivo de zero ou None, texto das pistas para o LLM)."""
    # Na nuvem, se o download da inicialização falhou (ou o app subiu antes do upload do deploy), tenta de novo
    # aqui; com os arquivos já no disco é só uma checagem de existência.
    await asyncio.to_thread(artifacts.ensure_downloaded)
    redacao = normalize_ocr_text(essay_text)
    t0 = time.perf_counter()
    answers = await ask_jev(tema, redacao)
    jev_ms = round((time.perf_counter() - t0) * 1000)
    feats = all_features(tema, redacao, answers)
    levels = await asyncio.to_thread(predict_levels, feats, redacao)  # CPU (e carga do modelo na 1ª vez)
    zero, avisos, dh = evaluate_gate(answers, word_count(redacao))
    if dh:
        levels[4] = 0
    hits = checklist_hits(answers, levels, artifacts.checklist())
    logger.info(
        "hybrid_graded",
        total=sum(levels) * 40,
        levels=levels,
        zero=zero,
        avisos=len(avisos),
        pistas=sum(len(v) for v in hits.values()),
        jev_ms=jev_ms,
        palavras=word_count(redacao),
    )
    return levels, zero, pistas_text(hits, answers, avisos)


async def correct_hybrid(input_block: str, tema: str, essay_text: str) -> str:
    """`input_block` é o mesmo bloco do modo `llm` (tema, motivadores, redação); aqui ganha as notas fixas."""
    levels, zero, pistas = await grade(tema, essay_text)
    if zero:
        bloco = HYBRID_ZERO_BLOCK.format(motivo=zero, pistas=pistas)
    else:
        notas = {c: lv * 40 for c, lv in zip(COMPS, levels)}
        bloco = HYBRID_GRADES_BLOCK.format(**notas, total=sum(notas.values()), pistas=pistas)
    feedback = await get_corrector().correct(input_block + bloco)
    feedback = _NEGRITO_DUPLO.sub(r"*\1*", feedback or "")
    if _VAZAMENTO.search(feedback):
        logger.warning("hybrid_feedback_mentions_mechanism")
    return feedback

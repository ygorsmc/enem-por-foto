"""OCR da foto da redação via Mistral OCR.

Adaptado do `MistralOCRParser.ocr_image` do projeto pai: a foto É o documento
inteiro, então não há enriquecimento visual — só a transcrição em markdown.
Levanta a exceção em falha definitiva; o fluxo decide a mensagem ao aluno.

Além do texto, pedimos a confiança por palavra (`confidence_scores_granularity=
"word"`) e devolvemos as palavras que o OCR leu com baixa certeza — o fluxo as
destaca no preview para o aluno conferir (letra difícil → leitura incerta). É só
triagem de atenção: confiança baixa não significa erro, apenas "vale checar".
"""

import base64
from dataclasses import dataclass, field

import structlog
from mistralai.client import Mistral
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings

logger = structlog.get_logger(__name__)

# Filtros da lista de palavras a conferir. O piso de 3 letras corta palavras
# funcionais ("de", "da", "no") de baixa confiança, mais ruído que sinal. A lista
# vem ordenada da MENOR confiança para a maior (pior primeiro) e é capada — numa
# foto de letra difícil o OCR fica incerto em dezenas de palavras (calibração nas
# redações reais: ~50 numa redação nota 800 vs. 0-2 numa nota 1000). O fluxo usa o
# tamanho da lista para decidir se aponta palavras ou pede releitura do texto todo.
_MIN_FLAGGED_WORD_LEN = 3
_MAX_FLAGGED_WORDS = 30

_client: Mistral | None = None


@dataclass
class OcrResult:
    """Texto transcrito + palavras que o OCR leu com baixa confiança."""

    text: str
    low_confidence_words: list[str] = field(default_factory=list)


def _get_client() -> Mistral:
    global _client
    if _client is None:
        if not settings.MISTRAL_API_KEY:
            raise ValueError("MISTRAL_API_KEY não configurada.")
        _client = Mistral(api_key=settings.MISTRAL_API_KEY)
    return _client


def _low_confidence_words(resp) -> list[str]:
    """Palavras com confiança abaixo do threshold, da MENOR para a maior confiança
    (pior primeiro), deduplicadas e capadas. Defensivo: a API só popula os scores
    quando pedimos granularidade."""
    threshold = settings.OCR_CONFIDENCE_THRESHOLD
    pairs: list[tuple[str, float]] = []
    for page in resp.pages:
        scores = getattr(page, "confidence_scores", None)
        for w in getattr(scores, "word_confidence_scores", None) or []:
            if w.confidence >= threshold:
                continue
            token = w.text.strip()
            if len(token) < _MIN_FLAGGED_WORD_LEN or not any(c.isalnum() for c in token):
                continue
            pairs.append((token, w.confidence))

    pairs.sort(key=lambda p: p[1])  # pior primeiro
    seen: set[str] = set()
    words: list[str] = []
    for token, _conf in pairs:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        words.append(token)
        if len(words) >= _MAX_FLAGGED_WORDS:
            break
    return words


@retry(wait=wait_exponential(multiplier=2, min=2, max=30), stop=stop_after_attempt(3), reraise=True)
async def ocr_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> OcrResult:
    """OCR de UMA imagem (foto de redação) → texto markdown + palavras incertas."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    resp = await _get_client().ocr.process_async(
        model="mistral-ocr-latest",
        document={"type": "image_url", "image_url": f"data:{mime_type};base64,{b64}"},
        confidence_scores_granularity="word",
    )
    text = "\n\n".join(
        p.markdown for p in resp.pages if getattr(p, "markdown", "")
    ).strip()
    low = _low_confidence_words(resp)
    if low:
        logger.info("ocr_low_confidence_words", count=len(low))
    return OcrResult(text=text, low_confidence_words=low)

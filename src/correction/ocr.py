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
import re
from dataclasses import dataclass, field

import structlog
from mistralai.client import Mistral
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

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

# Saída degenerada: o modelo entra em loop e "lê" números que não estão na folha — uma sequência longa
# de dígitos ("a228214126211226…") ou uma contagem ("5,6,7,…,100") — e perde o resto do texto. Visto no
# mistral-ocr-4 (2026-11-17). Redação de verdade não tem 15 dígitos seguidos nem lista de 15 números.
_DEGENERATE_RE = re.compile(r"\d{15,}|(?:\d{1,3}\s*,\s*){15,}")

# O OCR 4.x às vezes devolve a redação como tabela markdown de UMA coluna: cada parágrafo em "| … |" e uma
# linha "| --- |" depois do primeiro. As barras são marcação do OCR, não texto do aluno: removê-las não altera
# nada do que ele escreveu (invariante 5) e deixa a prévia, o LLM e o modo híbrido com parágrafos limpos.
# Linhas com mais de uma célula ("| 1 | texto |", linhas numeradas de modelos antigos) ficam como estão.
_ONE_COLUMN_ROW_RE = re.compile(r"^\|(?P<cell>[^|]*)\|$")
_ONE_COLUMN_SEPARATOR_RE = re.compile(r"^\|\s*:?-{3,}:?\s*\|$")


class OcrDegenerateError(ValueError):
    """A leitura veio com lixo do modelo. Repetir não adianta (mesmos bytes → mesma saída): nova foto."""


def looks_degenerate(text: str) -> bool:
    return bool(_DEGENERATE_RE.search(text))


def unwrap_single_column_table(text: str) -> str:
    """Tabela markdown de uma coluna → um parágrafo por linha da tabela (separados por linha em branco)."""
    out: list[str] = []
    changed = False
    for line in text.splitlines():
        stripped = line.strip()
        if _ONE_COLUMN_SEPARATOR_RE.match(stripped):
            changed = True
            continue
        row = _ONE_COLUMN_ROW_RE.match(stripped)
        if row:
            changed = True
            cell = row.group("cell").strip()
            if cell:
                out.extend([cell, ""])
            continue
        out.append(line)
    if not changed:
        return text
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


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


@retry(
    retry=retry_if_not_exception_type(OcrDegenerateError),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def ocr_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> OcrResult:
    """OCR de UMA imagem (foto de redação) → texto markdown + palavras incertas.

    Levanta `OcrDegenerateError` se a leitura vier com lixo do modelo: o fluxo pede outra foto em vez de
    mostrar o lixo ao aluno como se fosse a leitura dele.
    """
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    resp = await _get_client().ocr.process_async(
        model=settings.OCR_MODEL,
        document={"type": "image_url", "image_url": f"data:{mime_type};base64,{b64}"},
        confidence_scores_granularity="word",
    )
    text = "\n\n".join(
        p.markdown for p in resp.pages if getattr(p, "markdown", "")
    ).strip()
    text = unwrap_single_column_table(text)
    if looks_degenerate(text):
        logger.warning("ocr_degenerate_output", model=settings.OCR_MODEL, chars=len(text))
        raise OcrDegenerateError(f"leitura degenerada do {settings.OCR_MODEL}")
    low = _low_confidence_words(resp)
    if low:
        logger.info("ocr_low_confidence_words", count=len(low))
    return OcrResult(text=text, low_confidence_words=low)

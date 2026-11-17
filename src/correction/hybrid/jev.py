"""Cliente do Jev (TypeSafe AI, `POST /v1/systemone`): uma chamada com o estado {tema, redacao} e as 71 perguntas.

O modelo foi treinado com as respostas às 71 perguntas do registro v4. Ele usa diretamente 55 (uma por conceito),
mas as features combinadas (JEV_DOM, ex.: a incerteza média) foram calculadas no treino sobre TODAS as respostas —
por isso o bot pergunta as 71, exatamente como no treino. O custo vem quase todo do texto das perguntas
(~10,7 mil tokens de entrada; a redação é ~0,6 mil): ~US$ 0,00045 por chamada, saída gratuita.
"""

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.correction.hybrid.artifacts import TEMA_SENTINELA, questions_template

logger = structlog.get_logger(__name__)

API_URL = "https://api.typesafe.ai/v1/systemone"
TIMEOUT_S = 60.0


def _fill(obj, tema: str):
    """Troca o marcador do tema em todas as strings (algumas perguntas levam o tema no próprio texto)."""
    if isinstance(obj, str):
        return obj.replace(TEMA_SENTINELA, tema)
    if isinstance(obj, list):
        return [_fill(x, tema) for x in obj]
    if isinstance(obj, dict):
        return {k: _fill(v, tema) for k, v in obj.items()}
    return obj


def build_questions(tema: str) -> dict:
    return _fill(questions_template(), tema)


def parse_answers(resp: dict, expected: set[str]) -> dict:
    """Resposta da API → {pergunta: probabilidade/nível (float) | Choice (dict com choice e probabilities)}."""
    out: dict = {}
    for k, ans in (resp.get("answers") or {}).items():
        if ans.get("type") == "choice":
            out[k] = ans
        else:
            out[k] = float(ans["noul"]) if "noul" in ans else float(ans["score"])
    faltando = expected - set(out)
    if faltando:
        raise ValueError(f"Jev não respondeu {len(faltando)} perguntas: {sorted(faltando)[:5]}")
    return out


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3), reraise=True)
async def ask_jev(tema: str, redacao: str) -> dict:
    if not settings.JEV_API_KEY:
        raise ValueError("JEV_API_KEY não configurada (necessária no modo híbrido).")
    questions = build_questions(tema)
    payload = {
        "model": settings.JEV_MODEL,
        "state": {"tema": tema, "redacao": redacao},
        "questions": questions,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        r = await client.post(
            API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {settings.JEV_API_KEY}", "Accept": "application/json"},
        )
        r.raise_for_status()
        resp = r.json()
    usage = resp.get("usage") or {}
    logger.info("jev_answered", questions=len(questions), input_tokens=usage.get("input_tokens"))
    return parse_answers(resp, set(questions))

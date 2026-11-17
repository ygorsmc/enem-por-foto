"""Artefatos do fluxo híbrido, gerados no laboratório por `_local/scripts/jev_v4_export.py`.

Ficam em `src/correction/hybrid/artifacts/` (gitignorado: o modelo e as perguntas não vão para o repo
público). Carregados sob demanda e uma única vez por processo.
"""

import json
from functools import lru_cache
from pathlib import Path

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
TEMA_SENTINELA = "§TEMA§"


class ArtifactsMissingError(RuntimeError):
    """O modo híbrido foi ligado, mas os artefatos não foram gerados nesta máquina."""


def _path(nome: str) -> Path:
    p = ARTIFACTS_DIR / nome
    if not p.exists():
        raise ArtifactsMissingError(
            f"{p} não existe — gere com `PYTHONPATH=_local/scripts _local/.venv/bin/python "
            "_local/scripts/jev_v4_export.py` ou use CORRECTION_MODE=llm."
        )
    return p


@lru_cache(maxsize=1)
def questions_template() -> dict:
    with open(_path("questions.json"), encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def checklist() -> dict:
    with open(_path("checklist.json"), encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def model() -> dict:
    import joblib  # tardio: numpy/sklearn só carregam quando o modo híbrido é usado

    return joblib.load(_path("model.joblib"))

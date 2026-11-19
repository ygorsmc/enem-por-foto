"""Artefatos do fluxo híbrido, gerados no laboratório por `_local/scripts/jev_v4_export.py`.

Ficam em `src/correction/hybrid/artifacts/`, fora do git e fora da imagem Docker (o modelo e as perguntas não vão
para o repo nem para o pacote público no GHCR). Carregados sob demanda e uma única vez por processo.

De onde vêm:
  - local (`make dev`/`make up`): o docker-compose monta a pasta do disco, só leitura;
  - nuvem (deploy): o `deploy.sh` envia os arquivos para um contêiner PRIVADO do Blob Storage, e o bot os baixa
    por um link SAS só de leitura (`HYBRID_ARTIFACTS_URL`, segredo criado pelo Bicep) — ver `ensure_downloaded`.
"""

import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import structlog

from src.config import settings

logger = structlog.get_logger(__name__)

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
TEMA_SENTINELA = "§TEMA§"
FILES = ("model.joblib", "questions.json", "checklist.json", "meta.json")
_DOWNLOAD_TIMEOUT_S = 120.0


def ensure_downloaded() -> bool:
    """Baixa os artefatos que faltam, se `HYBRID_ARTIFACTS_URL` estiver configurada. → True se estão todos no disco.

    Bloqueante (rede + disco): chame fora do event loop (asyncio.to_thread). Barato quando já está tudo no disco.
    Cada arquivo é gravado num temporário e renomeado, então um download interrompido nunca deixa arquivo pela
    metade. O link nunca vai para o log: a parte de query é a assinatura de acesso.
    """
    faltando = [n for n in FILES if not (ARTIFACTS_DIR / n).exists()]
    if not faltando:
        return True
    url = settings.HYBRID_ARTIFACTS_URL
    if not url:
        return False
    import httpx

    base = urlsplit(url)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=_DOWNLOAD_TIMEOUT_S, follow_redirects=False) as client:
            for nome in faltando:
                arquivo = urlunsplit(base._replace(path=f"{base.path.rstrip('/')}/{nome}"))
                r = client.get(arquivo)
                r.raise_for_status()
                fd, tmp = tempfile.mkstemp(dir=ARTIFACTS_DIR, prefix=f".{nome}.")
                with os.fdopen(fd, "wb") as f:
                    f.write(r.content)
                os.replace(tmp, ARTIFACTS_DIR / nome)
                logger.info("hybrid_artifact_downloaded", file=nome, bytes=len(r.content))
    except Exception as e:
        logger.error(
            "hybrid_artifacts_download_failed",
            host=base.hostname,
            error_type=type(e).__name__,
            status=getattr(getattr(e, "response", None), "status_code", None),
        )
        return False
    return True


class ArtifactsMissingError(RuntimeError):
    """O modo híbrido foi ligado, mas os artefatos não foram gerados nesta máquina."""


def _path(nome: str) -> Path:
    p = ARTIFACTS_DIR / nome
    if not p.exists():
        raise ArtifactsMissingError(
            f"{p} não existe — local: gere com `PYTHONPATH=_local/scripts _local/.venv/bin/python "
            "_local/scripts/jev_v4_export.py`; nuvem: confira o upload do deploy.sh e HYBRID_ARTIFACTS_URL "
            "(log hybrid_artifacts_download_failed); ou use CORRECTION_MODE=llm."
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

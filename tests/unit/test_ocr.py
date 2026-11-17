"""Guarda de leitura degenerada do OCR (src/correction/ocr.py), com o cliente Mistral falso."""

import asyncio
from types import SimpleNamespace

import pytest

import src.correction.ocr as ocr

NORMAL = (
    "De acordo com a Constituição de 1988, artigo 5, todos são iguais perante a lei. "
    "Em 2023, 45% dos jovens (15 a 29 anos) relataram preconceito, segundo o IBGE."
)
# Saídas reais do mistral-ocr-4 (2026-11-17), encurtadas.
LIXO_DIGITOS = "Também, a228214126211226214226216226216226216226216226216226216226216"
LIXO_CONTAGEM = "em defesa de541," + ",".join(str(n) for n in range(5, 40))


class TestDegenerate:
    def test_texto_normal_com_numeros_passa(self):
        assert not ocr.looks_degenerate(NORMAL)

    @pytest.mark.parametrize("lixo", [LIXO_DIGITOS, LIXO_CONTAGEM])
    def test_lixo_do_modelo_e_detectado(self, lixo):
        assert ocr.looks_degenerate(NORMAL + " " + lixo)

    def test_ocr_degenerado_falha_sem_repetir(self, monkeypatch):
        chamadas = []

        async def process_async(**kw):
            chamadas.append(kw["model"])
            return SimpleNamespace(pages=[SimpleNamespace(markdown=NORMAL + " " + LIXO_DIGITOS)])

        fake = SimpleNamespace(ocr=SimpleNamespace(process_async=process_async))
        monkeypatch.setattr(ocr, "_get_client", lambda: fake)
        with pytest.raises(ocr.OcrDegenerateError):
            asyncio.run(ocr.ocr_image(b"x"))
        # Mesmos bytes → mesma saída: repetir só gastaria; o fluxo pede outra foto.
        assert chamadas == [ocr.settings.OCR_MODEL] and "latest" not in chamadas[0]

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
        assert chamadas == [ocr.settings.OCR_MODEL]


# Formato real do mistral-ocr-4-1 na redação 920 (2026-11-18), encurtado: tabela de uma coluna.
TABELA_UMA_COLUNA = (
    "|  O poema \"No meio do caminho\" compara os desafios a uma pedra. |\n"
    "| --- |\n"
    "|  Em primeira instância, cabe analisar a valorização dos povos. |\n"
    "|  Portanto, medidas são necessárias. |"
)


class TestTabelaUmaColuna:
    def test_desembrulha_em_paragrafos_sem_barras(self):
        texto = ocr.unwrap_single_column_table(TABELA_UMA_COLUNA)
        assert "|" not in texto and "---" not in texto
        assert texto.split("\n\n") == [
            'O poema "No meio do caminho" compara os desafios a uma pedra.',
            "Em primeira instância, cabe analisar a valorização dos povos.",
            "Portanto, medidas são necessárias.",
        ]

    def test_texto_comum_nao_muda(self):
        texto = "Primeiro parágrafo.\n\nSegundo parágrafo, com | no meio."
        assert ocr.unwrap_single_column_table(texto) == texto

    def test_tabela_de_varias_colunas_nao_muda(self):
        # Linhas numeradas (modelos antigos): o normalize_ocr_text do modo híbrido é que trata.
        texto = "| 1 | De acordo com a lei |\n| --- | --- |\n| 2 | todos são iguais |"
        assert ocr.unwrap_single_column_table(texto) == texto

    def test_ocr_image_entrega_texto_sem_tabela(self, monkeypatch):
        async def process_async(**kw):
            return SimpleNamespace(pages=[SimpleNamespace(markdown=TABELA_UMA_COLUNA)])

        fake = SimpleNamespace(ocr=SimpleNamespace(process_async=process_async))
        monkeypatch.setattr(ocr, "_get_client", lambda: fake)
        resultado = asyncio.run(ocr.ocr_image(b"x"))
        assert "|" not in resultado.text
        assert resultado.text.startswith('O poema "No meio do caminho"')

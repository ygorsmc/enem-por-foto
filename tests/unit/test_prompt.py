"""O prompt é o produto — estes testes evitam regressão silenciosa no template."""

from src.correction.corrector import (
    MAX_ESSAY_CHARS,
    build_correction_prompt,
)
from src.prompts import ENEM_CORRECTION_PROMPT, NO_MOTIVATORS


def test_format_fills_all_placeholders():
    """str.format não pode explodir (chave literal sem escape) nem deixar buraco."""
    prompt = build_correction_prompt("Tema X", "Texto motivador Y", "Redação Z")
    assert "Tema X" in prompt
    assert "Texto motivador Y" in prompt
    assert "Redação Z" in prompt
    # Nenhum placeholder sobrou sem preencher.
    for ph in ("{tema}", "{textos_motivadores}", "{texto_redacao}"):
        assert ph not in prompt


def test_template_has_no_stray_braces():
    """Qualquer chave nova no template precisa ser placeholder conhecido ou escapada."""
    ENEM_CORRECTION_PROMPT.format(tema="a", textos_motivadores="b", texto_redacao="c")


def test_no_motivators_placeholder():
    prompt = build_correction_prompt("Tema", None, "Redação")
    assert NO_MOTIVATORS in prompt
    prompt = build_correction_prompt("Tema", "   ", "Redação")
    assert NO_MOTIVATORS in prompt


def test_essay_is_truncated():
    prompt = build_correction_prompt("Tema", None, "x" * (MAX_ESSAY_CHARS + 5000))
    assert "x" * MAX_ESSAY_CHARS in prompt
    assert "x" * (MAX_ESSAY_CHARS + 1) not in prompt


def test_output_format_is_whatsapp_friendly():
    """A seção de saída exige dialeto WhatsApp — sem tabelas nem títulos '#'."""
    assert "NUNCA use tabelas markdown" in ENEM_CORRECTION_PROMPT
    assert "NOTA ESTIMADA" in ENEM_CORRECTION_PROMPT


def test_keeps_core_rubric_content():
    """As cinco competências e a triagem de nota zero continuam no template."""
    for marker in (
        "Competência I",
        "Competência II",
        "Competência III",
        "Competência IV",
        "Competência V",
        "Triagem",
        "direitos humanos",
        "repertório de bolso",
    ):
        assert marker in ENEM_CORRECTION_PROMPT, marker


def test_no_resubmission_flow():
    """Sem histórico não há comparação de versões — o parágrafo foi removido."""
    assert "nova versão" not in ENEM_CORRECTION_PROMPT.lower()


def test_no_ocr_excuse_clause():
    """Transcrição é tratada como fiel: nenhuma ressalva de erro de OCR/transcrição
    pode dar ao corretor uma desculpa pra ignorar desvios reais do aluno."""
    assert "OCR" not in ENEM_CORRECTION_PROMPT
    for phrase in ("artefato de transcrição", "erro de transcrição"):
        assert phrase not in ENEM_CORRECTION_PROMPT.lower()

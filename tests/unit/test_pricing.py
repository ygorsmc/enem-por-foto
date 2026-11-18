"""Custo em US$ por chamada (src/correction/pricing.py): tabela do DeepSeek por horário e preço do Jev."""

from datetime import UTC, datetime

import pytest

from src.correction import pricing

TERCA = datetime(2026, 11, 17, tzinfo=UTC)  # dia útil
SABADO = datetime(2026, 11, 21, tzinfo=UTC)


class TestPriceWindow:
    @pytest.mark.parametrize(
        "hora,esperado",
        [
            (0, "off_peak"),
            (1, "peak"),
            (3, "peak"),
            (4, "off_peak"),
            (5, "off_peak"),
            (6, "peak"),
            (9, "peak"),
            (10, "off_peak"),
            (19, "off_peak"),
        ],
    )
    def test_dia_util(self, hora, esperado):
        assert pricing.price_window(TERCA.replace(hour=hora, minute=30)) == esperado

    def test_fim_de_semana_e_sempre_fora_do_pico(self):
        assert pricing.price_window(SABADO.replace(hour=2)) == "off_peak"

    def test_converte_fuso(self):
        # 23h de segunda em Brasília = 02h de terça em UTC → pico
        from datetime import timedelta, timezone

        brasilia = timezone(timedelta(hours=-3))
        assert pricing.price_window(datetime(2026, 11, 16, 23, 0, tzinfo=brasilia)) == "peak"


class TestLlmCost:
    def test_flash_fora_do_pico(self):
        c = pricing.llm_cost("deepseek-flash", 6528, 1326, 7610, TERCA.replace(hour=19))
        assert c["input_cached_tokens"] == pytest.approx(6528 * 0.003 / 1e6)
        assert c["input"] == pytest.approx(1326 * 0.15 / 1e6)
        assert c["output"] == pytest.approx(7610 * 0.60 / 1e6)
        assert c["total"] == pytest.approx(0.0047845, abs=1e-6)  # a correção do teste no Telegram

    def test_pico_custa_o_dobro(self):
        fora = pricing.llm_cost("deepseek-flash", 6000, 1000, 8000, TERCA.replace(hour=19))
        pico = pricing.llm_cost("deepseek-flash", 6000, 1000, 8000, TERCA.replace(hour=2))
        assert pico["total"] == pytest.approx(2 * fora["total"])

    def test_apelido_antigo_cobra_como_flash(self):
        t = TERCA.replace(hour=19)
        assert pricing.llm_cost("deepseek-v4-flash", 1, 2, 3, t) == pricing.llm_cost(
            "deepseek-flash", 1, 2, 3, t
        )

    def test_modelo_sem_tabela(self):
        assert pricing.llm_cost("gemini-3.5-flash", 100, 100, 100) is None


def test_jev_so_cobra_entrada():
    assert pricing.jev_cost(10_678)["total"] == pytest.approx(0.000448, abs=1e-6)

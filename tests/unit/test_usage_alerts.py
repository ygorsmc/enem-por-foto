"""Alerta de uso do LLM para o dono do bot (src/usage_alerts.py) e o teto de saída do provedor OpenAI-compatível.

Sem rede: Redis fake (conftest), canal fake no lugar do Telegram e cliente OpenAI falso que só grava o pedido.
"""

import asyncio
from types import SimpleNamespace

import pytest

import src.channels.factory as channel_factory
from src import messages as m
from src import usage_alerts
from src.config import settings
from src.correction.providers.openai_compatible import OpenAICompatibleCorrector
from tests.unit.conftest import FakeChannel

run = asyncio.run


class TestCrossedMilestone:
    @pytest.mark.parametrize(
        ("total", "added", "esperado"),
        [
            (99_999, 99_999, None),  # ainda não chegou
            (100_000, 1, 100_000),  # chegou exatamente
            (130_000, 40_000, 100_000),  # passou no meio da chamada
            (150_000, 20_000, None),  # já tinha passado do 100 mil antes
            (310_000, 250_000, 300_000),  # pulou vários: um alerta só, o maior
        ],
    )
    def test_marcos(self, total, added, esperado):
        assert usage_alerts.crossed_milestone(total, added, 100_000) == esperado

    def test_passo_zero_desliga(self):
        assert usage_alerts.crossed_milestone(500_000, 500_000, 0) is None


@pytest.fixture
def admin_channel(monkeypatch):
    canal = FakeChannel()
    monkeypatch.setattr(channel_factory, "get_channel", lambda name=None: canal)
    monkeypatch.setattr(settings, "ADMIN_TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(settings, "USAGE_ALERT_EVERY_TOKENS", 100_000)
    return canal


class TestRecordLlmUsage:
    def test_avisa_o_dono_ao_cruzar_o_marco(self, admin_channel):
        async def drive():
            await usage_alerts.record_llm_usage("deepseek", 60_000, 0.02)
            await usage_alerts.record_llm_usage("deepseek", 60_000, 0.03)

        run(drive())
        assert len(admin_channel.sent) == 1
        _, texto = admin_channel.sent[0]
        assert texto == m.USAGE_ALERT.format(
            provider="DeepSeek", milestone="100.000", total="120.000", calls="2", cost="0,05"
        )

    def test_sem_marco_nao_avisa(self, admin_channel):
        run(usage_alerts.record_llm_usage("deepseek", 99_000, 0.01))
        assert admin_channel.sent == []

    def test_sem_chat_do_dono_nao_avisa_mas_conta(self, admin_channel, fake_redis, monkeypatch):
        monkeypatch.setattr(settings, "ADMIN_TELEGRAM_CHAT_ID", "")
        run(usage_alerts.record_llm_usage("deepseek", 150_000, 0.05))
        assert admin_channel.sent == []
        assert fake_redis.store["usage:llm_tokens"] == "150000"

    def test_falha_no_envio_nao_atrapalha_a_correcao(self, admin_channel, monkeypatch):
        async def quebrado(user_id, text, reply_to=None):
            raise ConnectionError("telegram fora")

        monkeypatch.setattr(admin_channel, "send_text", quebrado)
        run(usage_alerts.record_llm_usage("deepseek", 200_000, 0.1))  # não levanta

    def test_contadores_nao_guardam_nada_do_aluno(self, admin_channel, fake_redis):
        run(usage_alerts.record_llm_usage("deepseek", 1_000, 0.001))
        assert sorted(fake_redis.store) == ["usage:llm_calls", "usage:llm_cost_usd", "usage:llm_tokens"]


def _fake_openai(capturado: dict, finish_reason: str = "stop"):
    async def create(**kwargs):
        capturado.update(kwargs)
        usage = SimpleNamespace(
            prompt_tokens=7_000,
            completion_tokens=9_000,
            prompt_cache_hit_tokens=6_500,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=6_000),
        )
        choice = SimpleNamespace(message=SimpleNamespace(content="feedback"), finish_reason=finish_reason)
        return SimpleNamespace(usage=usage, choices=[choice])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


class TestTetoDeSaida:
    def test_deepseek_envia_max_tokens_e_conta_o_uso(self, fake_redis, monkeypatch):
        monkeypatch.setattr(settings, "ADMIN_TELEGRAM_CHAT_ID", "")
        capturado: dict = {}
        corretor = OpenAICompatibleCorrector(
            "deepseek", "chave", "deepseek-flash", reasoning_effort="high", max_output_tokens=32_000
        )
        corretor._client = _fake_openai(capturado)
        assert run(corretor.correct("bloco")) == "feedback"
        assert capturado["max_tokens"] == 32_000
        assert "max_completion_tokens" not in capturado
        assert fake_redis.store["usage:llm_tokens"] == "16000"  # entrada + saída

    def test_openai_usa_max_completion_tokens(self, monkeypatch):
        capturado: dict = {}
        corretor = OpenAICompatibleCorrector(
            "openai", "chave", "gpt-5", max_output_tokens=32_000, max_tokens_param="max_completion_tokens"
        )
        corretor._client = _fake_openai(capturado)
        run(corretor.correct("bloco"))
        assert capturado["max_completion_tokens"] == 32_000 and "max_tokens" not in capturado

    def test_sem_teto_nao_envia_o_campo(self):
        capturado: dict = {}
        corretor = OpenAICompatibleCorrector("maritaca", "chave", "sabia-4")
        corretor._client = _fake_openai(capturado)
        run(corretor.correct("bloco"))
        assert "max_tokens" not in capturado and "max_completion_tokens" not in capturado

    def test_factory_aplica_o_teto_de_32_mil_no_deepseek(self, monkeypatch):
        from src.correction import factory

        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "chave")
        monkeypatch.setattr(factory, "_correctors", {})
        corretor = factory.get_corrector("deepseek")
        assert corretor._max_output_tokens == settings.LLM_MAX_OUTPUT_TOKENS == 32_000
        assert corretor._max_tokens_param == "max_tokens"

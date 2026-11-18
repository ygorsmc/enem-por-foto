"""Langfuse opcional (src/observability.py): desligado sem chaves e, ligado, só números — nunca texto.

Nenhum teste chama a rede: o cliente do Langfuse é falso.
"""

import asyncio
from types import SimpleNamespace

import pytest
from opentelemetry import trace

import src.observability as obs
from src.config import settings
from src.correction.providers import openai_compatible as oc


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(obs, "_client", None)
    monkeypatch.setattr(obs, "_init_done", False)


class _FakeObs:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def update(self, **kw):
        self.log.append(("update", kw))


class _FakeLangfuse:
    instances: list = []

    def __init__(self, **kw):
        self.kw = kw
        self.calls: list = []
        _FakeLangfuse.instances.append(self)

    def start_as_current_observation(self, **kw):
        self.calls.append(("start", kw))
        return _FakeObs(self.calls)


def _ligar(monkeypatch):
    import langfuse

    _FakeLangfuse.instances.clear()
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "pk-lf-teste")
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", "sk-lf-teste")
    monkeypatch.setattr(langfuse, "Langfuse", _FakeLangfuse)


class TestDesligado:
    def test_sem_chaves_tudo_e_no_op(self, monkeypatch):
        monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "")
        with obs.correction_trace(mode="llm"):
            with obs.generation("llm", "deepseek-flash") as gen:
                gen.update(usage_details={"input": 1}, cost_details={"total": 0.1})
        assert obs._get_client() is None


class TestLigado:
    def test_provider_privado_e_filtro(self, monkeypatch):
        _ligar(monkeypatch)
        assert obs._get_client() is not None
        kw = _FakeLangfuse.instances[0].kw
        # Trava 2: provider próprio, e o global continua vazio (o SDK do Mistral não cria spans do OCR)
        assert kw["tracer_provider"] is not trace.get_tracer_provider()
        assert isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider)
        filtro = kw["should_export_span"]
        span = lambda nome: SimpleNamespace(instrumentation_scope=SimpleNamespace(name=nome))  # noqa: E731
        assert filtro(span("langfuse-sdk"))
        assert not filtro(span("mistralai_sdk_tracer"))
        assert not filtro(SimpleNamespace(instrumentation_scope=None))

    def test_nunca_envia_texto(self, monkeypatch):
        _ligar(monkeypatch)
        with obs.correction_trace(mode="hibrido"):
            with obs.generation("llm", "deepseek-flash", effort="high") as gen:
                gen.update(
                    usage_details={"input": 10, "output": 5, "total": 15}, cost_details={"total": 0.001}
                )
        calls = _FakeLangfuse.instances[0].calls
        assert [c[0] for c in calls] == ["start", "start", "update"]
        for _, kw in calls:
            assert "input" not in kw and "output" not in kw  # input/output do Langfuse = texto

    def test_falha_do_sdk_nao_derruba_a_correcao(self, monkeypatch):
        _ligar(monkeypatch)

        def quebra(self, **kw):
            raise RuntimeError("Langfuse fora do ar")

        monkeypatch.setattr(_FakeLangfuse, "start_as_current_observation", quebra)
        with obs.generation("jev", "jev-1.14.0") as gen:
            gen.update(usage_details={"input": 1})  # segue sem exceção


class TestCustoNoProvedor:
    def test_deepseek_registra_tokens_e_custo(self, monkeypatch):
        _ligar(monkeypatch)
        usage = SimpleNamespace(
            prompt_tokens=7854,
            completion_tokens=7610,
            prompt_cache_hit_tokens=6528,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=3989),
        )
        resposta = SimpleNamespace(
            usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

        async def create(**kw):
            return resposta

        logs = []
        monkeypatch.setattr(oc, "logger", SimpleNamespace(info=lambda ev, **kw: logs.append((ev, kw))))
        corr = oc.OpenAICompatibleCorrector("deepseek", "k", "deepseek-flash", reasoning_effort="high")
        corr._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        assert asyncio.run(corr.correct("redação")) == "ok"

        ev, kw = logs[0]
        assert kw["prompt_tokens"] == 7854 and kw["prompt_cache_miss_tokens"] == 1326
        assert kw["cost_usd"] > 0 and kw["price_window"] in ("peak", "off_peak")
        update = [c for c in _FakeLangfuse.instances[0].calls if c[0] == "update"][0][1]
        assert update["usage_details"]["output_reasoning_tokens"] == 3989
        assert update["cost_details"]["total"] == pytest.approx(kw["cost_usd"], abs=1e-6)

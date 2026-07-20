"""Namespace de chave Redis (REDIS_NAMESPACE) — permite dois bots dividirem o
mesmo banco (ex.: um único Upstash free tier) sem colidir estado."""

from src.config import settings
from src.flow.states import _consent_key, _flow_key
from src.rate_limit import daily_count_key
from src.redis_client import redis_key


class TestRedisNamespace:
    def test_no_prefix_by_default(self, monkeypatch):
        monkeypatch.setattr(settings, "REDIS_NAMESPACE", "")
        assert redis_key("flow", "telegram", "1") == "flow:telegram:1"

    def test_prefix_applied_when_set(self, monkeypatch):
        monkeypatch.setattr(settings, "REDIS_NAMESPACE", "enem")
        assert redis_key("flow", "telegram", "1") == "enem:flow:telegram:1"

    def test_all_key_builders_respect_namespace(self, monkeypatch):
        monkeypatch.setattr(settings, "REDIS_NAMESPACE", "enem")
        assert _flow_key("telegram", "42").startswith("enem:flow:")
        assert _consent_key("telegram", "42").startswith("enem:consent:")
        assert daily_count_key("telegram", "42").startswith("enem:essay_count:")

    def test_two_namespaces_do_not_collide(self, monkeypatch):
        monkeypatch.setattr(settings, "REDIS_NAMESPACE", "enem")
        enem = _flow_key("telegram", "42")
        monkeypatch.setattr(settings, "REDIS_NAMESPACE", "")
        act = _flow_key("telegram", "42")
        assert enem != act  # mesmo usuário, mesmo canal → chaves distintas

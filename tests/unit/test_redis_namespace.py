"""Namespace de chave Redis (REDIS_NAMESPACE) — prefixo opcional útil quando o
mesmo banco é compartilhado entre múltiplos ambientes/deploys."""

from src.config import settings
from src.flow.states import _consent_key, _flow_key
from src.rate_limit import daily_count_key
from src.redis_client import redis_key


class TestRedisNamespace:
    def test_no_prefix_by_default(self, monkeypatch):
        monkeypatch.setattr(settings, "REDIS_NAMESPACE", "")
        assert redis_key("flow", "telegram", "1") == "flow:telegram:1"

    def test_prefix_applied_when_set(self, monkeypatch):
        monkeypatch.setattr(settings, "REDIS_NAMESPACE", "ns1")
        assert redis_key("flow", "telegram", "1") == "ns1:flow:telegram:1"

    def test_all_key_builders_respect_namespace(self, monkeypatch):
        monkeypatch.setattr(settings, "REDIS_NAMESPACE", "ns1")
        assert _flow_key("telegram", "42").startswith("ns1:flow:")
        assert _consent_key("telegram", "42").startswith("ns1:consent:")
        assert daily_count_key("telegram", "42").startswith("ns1:essay_count:")

    def test_different_namespaces_do_not_collide(self, monkeypatch):
        monkeypatch.setattr(settings, "REDIS_NAMESPACE", "ns1")
        prefixed = _flow_key("telegram", "42")
        monkeypatch.setattr(settings, "REDIS_NAMESPACE", "")
        unprefixed = _flow_key("telegram", "42")
        assert prefixed != unprefixed  # mesmo usuário, mesmo canal → chaves distintas

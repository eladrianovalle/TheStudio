from unittest import mock

from studio.health import check_ollama_health


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def test_check_ollama_health_happy_path(monkeypatch):
    def fake_get(url, timeout):
        if url.endswith("/api/tags"):
            return _Response({"models": [{"name": "llama3.1:8b"}]})
        if url.endswith("/api/version"):
            return _Response({"version": "0.1.0"})
        raise AssertionError("Unexpected URL")

    monkeypatch.setattr("studio.health.requests.get", fake_get)

    healthy, detail = check_ollama_health("ollama/llama3.1:8b", "http://localhost:11434")

    assert healthy is True
    assert "Ollama ready" in detail
    assert "v0.1.0" in detail


def test_check_ollama_health_missing_model(monkeypatch):
    def fake_get(url, timeout):
        assert url.endswith("/api/tags")
        return _Response({"models": [{"name": "phi3"}]})

    monkeypatch.setattr("studio.health.requests.get", fake_get)

    healthy, detail = check_ollama_health("ollama/llama3.1:8b", "http://localhost:11434")

    assert healthy is False
    assert "missing model" in detail.lower()

"""Tests for the Slack/n8n run-digest integration."""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from integrations import slack_digest as sd


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def run_dir(tmp_path):
    """A run directory with a finalized run.json and summary.md."""
    d = tmp_path / "run_design_20260625_1430"
    d.mkdir()
    (d / "run.json").write_text(
        json.dumps(
            {
                "run_id": "run_design_20260625_1430",
                "phase": "design",
                "status": "COMPLETED",
                "verdict": "APPROVED",
                "iterations_run": 3,
                "updated_iso": "2026-06-25T14:30:00+00:00",
                "summary_path": "summary.md",
            }
        ),
        encoding="utf-8",
    )
    (d / "summary.md").write_text("# Summary\nViable cozy farming sim.", encoding="utf-8")
    return d


class _FakeResp:
    """Minimal context-manager stand-in for urllib's response."""

    def __init__(self, status, body=b"ok"):
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


# --------------------------------------------------------------------------- #
# Config loading
# --------------------------------------------------------------------------- #
def test_load_config_absent_returns_empty(tmp_path):
    assert sd.load_integrations_config(tmp_path) == {}


def test_load_config_reads_toml(tmp_path):
    studio = tmp_path / ".studio"
    studio.mkdir()
    (studio / "integrations.toml").write_text(
        '[slack]\nenabled = true\nwebhook_url_env = "SLACK_WEBHOOK_URL"\n',
        encoding="utf-8",
    )
    cfg = sd.load_integrations_config(tmp_path)
    assert cfg["slack"]["enabled"] is True


def test_load_config_invalid_toml_raises(tmp_path):
    studio = tmp_path / ".studio"
    studio.mkdir()
    (studio / "integrations.toml").write_text("not = = valid", encoding="utf-8")
    with pytest.raises(sd.IntegrationsConfigError):
        sd.load_integrations_config(tmp_path)


def test_resolve_secret_prefers_env(monkeypatch):
    monkeypatch.setenv("MY_HOOK", "https://hooks.slack.com/services/x")
    cfg = {"webhook_url_env": "MY_HOOK", "webhook_url": "literal"}
    assert sd._resolve_secret(cfg, "webhook_url").endswith("/x")


def test_resolve_secret_falls_back_to_literal(monkeypatch):
    monkeypatch.delenv("MY_HOOK", raising=False)
    cfg = {"webhook_url_env": "MY_HOOK", "webhook_url": "literal-url"}
    assert sd._resolve_secret(cfg, "webhook_url") == "literal-url"


# --------------------------------------------------------------------------- #
# Payload builders
# --------------------------------------------------------------------------- #
def test_build_slack_blocks_shape():
    meta = {"phase": "design", "run_id": "r1", "status": "COMPLETED", "verdict": "APPROVED"}
    payload = sd.build_slack_blocks(meta)
    assert payload["text"]  # required fallback present
    types = [b["type"] for b in payload["blocks"]]
    assert types == ["header", "section", "divider", "context"]
    field_text = " ".join(f["text"] for f in payload["blocks"][1]["fields"])
    assert "APPROVED" in field_text and "design" in field_text


def test_build_n8n_payload_is_flat():
    meta = {"phase": "tech", "run_id": "r2", "status": "COMPLETED", "verdict": "REJECTED"}
    payload = sd.build_n8n_payload(meta, "x" * 5000)
    assert payload["source"] == "TheGameStudio"
    assert payload["event"] == "run.completed"
    assert payload["verdict"] == "REJECTED"
    assert len(payload["summary_text"]) <= sd._SUMMARY_MAX_CHARS


# --------------------------------------------------------------------------- #
# Transport (urllib mocked)
# --------------------------------------------------------------------------- #
def test_post_json_success(monkeypatch):
    monkeypatch.setattr(sd.urllib.request, "urlopen", lambda *a, **k: _FakeResp(200, b"ok"))
    ok, detail = sd.post_json("http://x", {"a": 1})
    assert ok and "200" in detail


def test_post_json_http_error_is_soft(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.HTTPError("http://x", 400, "Bad", {}, io.BytesIO(b"invalid_payload"))

    monkeypatch.setattr(sd.urllib.request, "urlopen", boom)
    ok, detail = sd.post_json("http://x", {"a": 1})
    assert ok is False and "400" in detail


def test_post_json_timeout_is_soft(monkeypatch):
    def boom(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(sd.urllib.request, "urlopen", boom)
    ok, detail = sd.post_json("http://x", {"a": 1})
    assert ok is False and "unreachable" in detail


def test_post_json_retries_on_429(monkeypatch):
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                "http://x", 429, "Too Many", {"Retry-After": "0"}, io.BytesIO(b"rate_limited")
            )
        return _FakeResp(200, b"ok")

    monkeypatch.setattr(sd.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(sd.time, "sleep", lambda s: None)
    ok, _ = sd.post_json("http://x", {"a": 1})
    assert ok is True and calls["n"] == 2


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def test_notify_run_no_targets(run_dir):
    results = sd.notify_run(run_dir, {})
    assert results == ["no targets enabled (see .studio/integrations.toml)"]


def test_notify_run_missing_run_json(tmp_path):
    with pytest.raises(FileNotFoundError):
        sd.notify_run(tmp_path, {"slack": {"enabled": True}})


def test_notify_run_dry_run_does_not_post(run_dir, monkeypatch):
    monkeypatch.setenv("HOOK", "http://slack")
    called = {"posted": False}
    monkeypatch.setattr(
        sd.urllib.request, "urlopen",
        lambda *a, **k: called.__setitem__("posted", True),
    )
    cfg = {"slack": {"enabled": True, "webhook_url_env": "HOOK"}}
    results = sd.notify_run(run_dir, cfg, dry_run=True)
    assert called["posted"] is False
    assert any("dry-run" in r for r in results)


def test_notify_run_posts_to_enabled_targets(run_dir, monkeypatch):
    monkeypatch.setenv("SLACK_HOOK", "http://slack")
    monkeypatch.setenv("N8N_HOOK", "http://n8n")
    sent = []

    def capture(req, *a, **k):
        sent.append((req.full_url, dict(req.header_items()), req.data))
        return _FakeResp(200, b"ok")

    monkeypatch.setattr(sd.urllib.request, "urlopen", capture)
    cfg = {
        "slack": {"enabled": True, "webhook_url_env": "SLACK_HOOK"},
        "n8n": {
            "enabled": True,
            "webhook_url_env": "N8N_HOOK",
            "auth_header": "X-API-Key",
            "auth_value": "sekret",
        },
    }
    results = sd.notify_run(run_dir, cfg)
    assert all("ok" in r for r in results)
    urls = [u for u, _, _ in sent]
    assert "http://slack" in urls and "http://n8n" in urls
    # n8n auth header is forwarded (urllib title-cases header names)
    n8n_headers = next(h for u, h, _ in sent if u == "http://n8n")
    assert n8n_headers.get("X-api-key") == "sekret"


def test_notify_run_skips_target_without_url(run_dir, monkeypatch):
    monkeypatch.delenv("MISSING", raising=False)
    cfg = {"slack": {"enabled": True, "webhook_url_env": "MISSING"}}
    results = sd.notify_run(run_dir, cfg)
    assert results == ["slack: skipped (no webhook URL configured)"]

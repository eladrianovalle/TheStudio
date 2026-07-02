"""
Post a run digest to a Slack Incoming Webhook and/or an n8n Webhook node.

Both targets are "HTTP POST a JSON body to a URL", so a single stdlib
``urllib`` transport (:func:`post_json`) serves both; only the payload schema
and auth differ. Slack gets a Block Kit message (:func:`build_slack_blocks`);
n8n gets a flat run-digest JSON (:func:`build_n8n_payload`) it can fan out from.

Configuration lives in ``.studio/integrations.toml`` (loaded with the same
tomllib pattern as ``persona_overrides.py``). Webhook URLs are secrets and are
resolved from environment variables named in the config, never stored in the
repo. The integration is disabled unless a target is explicitly enabled.

File schema (all tables/keys optional; absent → that target is off)::

    [slack]
    enabled = true
    webhook_url_env = "SLACK_WEBHOOK_URL"   # env var holding the secret URL

    [n8n]
    enabled = false
    webhook_url_env = "N8N_WEBHOOK_URL"
    auth_header = "X-API-Key"               # optional (n8n Header Auth)
    auth_value_env = "N8N_WEBHOOK_KEY"      # optional secret for that header

Notification failures are soft: :func:`post_json` never raises and
:func:`notify_run` only returns human-readable result strings, so a webhook
problem can never break the run it is reporting on.
"""
from __future__ import annotations

from config_loading import tomllib

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple


INTEGRATIONS_FILENAME = "integrations.toml"
_SUMMARY_MAX_CHARS = 600
# Slack section text objects cap at 3000 chars; leave headroom for the
# truncation notice appended below.
_SLACK_SUMMARY_MAX_CHARS = 2700
_USER_AGENT = "TheGameStudio-digest/1.0"


class IntegrationsConfigError(RuntimeError):
    """Raised when ``.studio/integrations.toml`` is present but invalid."""


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def load_integrations_config(project_root: Path) -> Dict[str, Dict]:
    """Load ``<project_root>/.studio/integrations.toml``.

    Returns an empty dict when the file is absent. Raises
    :class:`IntegrationsConfigError` on malformed TOML.
    """
    path = Path(project_root) / ".studio" / INTEGRATIONS_FILENAME
    if not path.is_file():
        return {}

    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise IntegrationsConfigError(
            f"Integrations config at {path} is not valid TOML: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise IntegrationsConfigError(
            f"Integrations config at {path} must be a table."
        )
    return data


def _resolve_secret(target_cfg: Dict, key: str) -> Optional[str]:
    """Resolve a secret strictly from the ``<key>_env`` env-var indirection.

    Secrets (webhook URLs, auth values) must never live in the committed config,
    so there is deliberately no literal ``<key>`` fallback; only the named
    environment variable is read. Returns None if unset/empty.
    """
    env_name = target_cfg.get(f"{key}_env")
    if not env_name:
        return None
    value = os.environ.get(env_name)
    return value.strip() if value and value.strip() else None


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #
def post_json(
    url: str,
    payload: Dict,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
    max_retries: int = 2,
) -> Tuple[bool, str]:
    """POST ``payload`` as JSON to ``url``. Never raises.

    Returns ``(ok, detail)`` where ``ok`` is True for any 2xx response.
    Honors HTTP 429 by sleeping ``Retry-After`` seconds and retrying.
    """
    data = json.dumps(payload).encode("utf-8")
    base_headers = {"Content-Type": "application/json", "User-Agent": _USER_AGENT}
    if headers:
        base_headers.update(headers)

    for attempt in range(max_retries + 1):
        req = urllib.request.Request(
            url, data=data, headers=base_headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "replace").strip()
                ok = 200 <= resp.status < 300
                return ok, f"HTTP {resp.status} {body[:120]!r}"
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace").strip()
            if exc.code == 429 and attempt < max_retries:
                retry_after = _retry_after_seconds(exc)
                time.sleep(retry_after)
                continue
            return False, f"HTTP {exc.code} {body[:120]!r}"
        except (urllib.error.URLError, TimeoutError) as exc:
            return False, f"unreachable: {exc}"

    return False, "exhausted retries"


def _retry_after_seconds(exc: urllib.error.HTTPError) -> int:
    raw = exc.headers.get("Retry-After", "1") if exc.headers else "1"
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


# --------------------------------------------------------------------------- #
# Payload builders
# --------------------------------------------------------------------------- #
def _status_icon(status: str) -> str:
    return ":white_check_mark:" if status.upper() == "COMPLETED" else ":warning:"


def _md_to_slack(md: str, *, max_chars: int = _SLACK_SUMMARY_MAX_CHARS) -> str:
    """Convert a markdown summary into Slack ``mrkdwn``, truncated to ``max_chars``.

    Slack mrkdwn is not CommonMark: headings (``#``) don't render, bold is
    ``*one-star*`` not ``**two-star**``, and ``-``/``*`` bullets show literally.
    This does the minimal, robust conversion so the digest reads cleanly:
    headings → bold lines, ``- ``/``* `` bullets → ``• ``, ``**x**`` → ``*x*``.
    """
    lines: List[str] = []
    for raw in md.splitlines():
        line = raw.rstrip()
        heading = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if heading:
            lines.append(f"*{heading.group(1).strip()}*")
            continue
        line = re.sub(r"^(\s*)[-*]\s+", r"\1• ", line)
        lines.append(line)
    text = "\n".join(lines)
    # Collapse CommonMark bold/italic markers to Slack's single-star bold.
    text = text.replace("**", "*")
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n_… truncated — see the full doc below._"
    return text


def build_slack_blocks(
    meta: Dict, summary_text: str = "", doc_path: str = ""
) -> Dict:
    """Build a Slack Block Kit digest payload from a run.json ``meta`` dict.

    Includes a top-level ``text`` fallback (required by Slack), a header, a
    two-column field section, the run ``summary`` body (converted to Slack
    mrkdwn and truncated), a pointer to the final doc, and a context footer.
    """
    phase = str(meta.get("phase", "?"))
    run_id = str(meta.get("run_id", "?"))
    status = str(meta.get("status", "?"))
    verdict = str(meta.get("verdict") or "N/A")
    when = str(meta.get("updated_iso") or meta.get("created_display") or "")
    iterations = meta.get("iterations_run")

    footer = "TheGameStudio digest"
    if iterations is not None:
        footer += f" · {iterations} iteration(s)"
    if when:
        footer += f" · {when}"

    blocks: List[Dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Run Summary", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Status:*\n{_status_icon(status)} {status}"},
                {"type": "mrkdwn", "text": f"*Verdict:*\n{verdict}"},
                {"type": "mrkdwn", "text": f"*Phase:*\n{phase}"},
                {"type": "mrkdwn", "text": f"*Run ID:*\n`{run_id}`"},
            ],
        },
    ]

    body = _md_to_slack(summary_text) if summary_text else ""
    if body:
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": body}})

    if doc_path:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Final doc:*\n`{doc_path}`"},
            }
        )

    blocks.append({"type": "divider"})
    blocks.append(
        {"type": "context", "elements": [{"type": "mrkdwn", "text": footer}]}
    )

    return {
        "text": f"Studio run summary — {phase} — {verdict}",
        "blocks": blocks,
    }


def build_n8n_payload(meta: Dict, summary_text: str = "") -> Dict:
    """Build a flat run-digest payload for an n8n Webhook node.

    Flat keys are addressable downstream as ``$json.body.<field>``.
    """
    return {
        "source": "TheGameStudio",
        "event": "run.completed",
        "phase": meta.get("phase"),
        "run_id": meta.get("run_id"),
        "status": meta.get("status"),
        "verdict": meta.get("verdict") or "N/A",
        "iterations_run": meta.get("iterations_run"),
        "summary_path": meta.get("summary_path"),
        "summary_text": summary_text[:_SUMMARY_MAX_CHARS],
        "timestamp": meta.get("updated_iso") or meta.get("created_iso"),
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _summary_doc_path(run_dir: Path, meta: Dict) -> str:
    """Absolute path to the run's summary doc, for a pointer in the digest."""
    name = meta.get("summary_path") or "summary.md"
    p = Path(name)
    if not p.is_absolute():
        p = run_dir / p.name
    return str(p.resolve())


def _read_summary_text(run_dir: Path, meta: Dict) -> str:
    name = meta.get("summary_path") or "summary.md"
    summary_path = Path(name)
    if not summary_path.is_absolute():
        summary_path = run_dir / summary_path.name
    if summary_path.is_file():
        return summary_path.read_text(encoding="utf-8").strip()
    return ""


# The Slack body prefers a short, plain-language digest when the run authored
# one. The full summary.md is often dense and technical and gets truncated. The
# "Final doc" pointer always targets the full summary regardless.
_DIGEST_CANDIDATES = ("digest.md", "summary_human.md")


def _read_digest_text(run_dir: Path, meta: Dict) -> str:
    """Prefer a plain-language ``digest.md`` for the Slack body; else the summary."""
    for name in _DIGEST_CANDIDATES:
        candidate = run_dir / name
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8").strip()
            if text:
                return text
    return _read_summary_text(run_dir, meta)


def notify_run(
    run_dir: Path,
    config: Dict,
    *,
    dry_run: bool = False,
) -> List[str]:
    """Post the run digest to every enabled target. Returns result strings.

    Reads ``run.json`` from ``run_dir``. Each enabled target is posted
    independently; a failure on one is reported but does not affect the other.
    With ``dry_run=True`` the payloads are built and reported but not sent.
    """
    run_dir = Path(run_dir)
    meta_path = run_dir / "run.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"No run.json at {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    results: List[str] = []

    slack_cfg = config.get("slack", {})
    if slack_cfg.get("enabled"):
        body_text = _read_digest_text(run_dir, meta)
        results.append(
            _dispatch(
                "slack",
                _resolve_secret(slack_cfg, "webhook_url"),
                build_slack_blocks(
                    meta, body_text, _summary_doc_path(run_dir, meta)
                ),
                headers=None,
                dry_run=dry_run,
            )
        )

    n8n_cfg = config.get("n8n", {})
    if n8n_cfg.get("enabled"):
        headers = None
        auth_header = n8n_cfg.get("auth_header")
        if auth_header:
            auth_value = _resolve_secret(n8n_cfg, "auth_value")
            if auth_value:
                headers = {auth_header: auth_value}
        results.append(
            _dispatch(
                "n8n",
                _resolve_secret(n8n_cfg, "webhook_url"),
                build_n8n_payload(meta, _read_summary_text(run_dir, meta)),
                headers=headers,
                dry_run=dry_run,
            )
        )

    if not results:
        results.append("no targets enabled (see .studio/integrations.toml)")
    return results


def _dispatch(
    name: str,
    url: Optional[str],
    payload: Dict,
    *,
    headers: Optional[Dict[str, str]],
    dry_run: bool,
) -> str:
    if not url:
        return f"{name}: skipped (no webhook URL configured)"
    if dry_run:
        return f"{name}: dry-run → {json.dumps(payload)}"
    ok, detail = post_json(url, payload, headers=headers)
    status = "ok" if ok else "FAILED"
    return f"{name}: {status} ({detail})"

# TICKET: Slack / n8n webhook digest for completed runs

**Type:** Feature · **Component:** `studio/integrations/` (new) · **Priority:** P2
**Status:** ✅ Shipped — PR #21 (merged 2026-06-25). Slack target verified live (HTTP 200).
n8n target: code shipped; activation tracked in `TICKET-n8n-activation.md`.
**Author:** Adriano Valle · **Date:** 2026-06-25

> **Decisions (locked):** `notify` CLI is the primary trigger; auto-fire-on-finalize
> ships in the same PR but **default-disabled**. Both **Slack + n8n** targets in v1.

## Summary

Add a small, stdlib-only outbound webhook integration that posts a **run digest**
(phase, run id, status, verdict, short summary, link) to a configurable HTTP
endpoint when a run is finalized. The same transport targets either a **Slack
Incoming Webhook** directly or an **n8n Webhook node** (which can then fan out to
Slack, email, a database, etc.).

Concretely: a new module `studio/integrations/slack_digest.py`, a `notify`
CLI subcommand (`python studio/run_phase.py notify --run-dir ...`), an optional
auto-fire at the end of `finalize`, and config via `.studio/integrations.toml`
(+ env-var secrets).

## Motivation

- Studio runs currently terminate silently — the operator must check
  `output/index.md` / `knowledge/run_log.md` to learn a run finished.
- A post-finalize digest gives teams a passive "run X finished, verdict
  APPROVED" feed in Slack, and an n8n target turns Studio into a node any
  automation can build on.
- It is the first **outbound integration** in the repo and establishes the
  `studio/integrations/` pattern.

## Goals / Non-goals

**Goals**
- One small module, stdlib only (`urllib.request` + `json` + `tomllib`/`tomli`).
- Works against a Slack Incoming Webhook URL *and* an n8n Webhook URL with the
  same code path; payload schema differs per target, transport is identical.
- Config-driven, secrets never committed. Disabled by default.
- Failures are **soft** — a notification error must never fail a run or finalize.
- Tested with `urllib` mocked (no real network in CI).

**Non-goals**
- No Slack OAuth app / bot tokens / interactivity — Incoming Webhooks only.
- No inbound webhooks / no server. Outbound POST only.
- No new third-party dependencies. No retry queue / persistence beyond a single
  inline retry on HTTP 429.

## Design

### Module: `studio/integrations/slack_digest.py`
Separate **transport** from **payload** (the one thing that genuinely differs
between Slack and n8n):

```python
def post_json(url, payload, headers=None, timeout=10.0, max_retries=2) -> bool
    # urllib POST; treat 2xx as success; honor 429 Retry-After; never raises.

def build_slack_blocks(meta: dict) -> dict          # Block Kit: header + fields + context
def build_n8n_payload(meta: dict, summary_text: str) -> dict   # flat run-digest JSON

def notify_run(run_dir: Path, config: dict) -> list[str]
    # reads run.json + summary.md, builds per-target payloads, posts to each
    # enabled target, returns a list of human-readable result strings.
```

### Config: `.studio/integrations.toml` (loaded with the existing tomllib pattern, cf. `persona_overrides.py:66`)
```toml
[slack]
enabled = true
# URL is a secret — read from env, NOT stored here:
webhook_url_env = "SLACK_WEBHOOK_URL"

[n8n]
enabled = false
webhook_url_env = "N8N_WEBHOOK_URL"
auth_header = "X-API-Key"          # optional; n8n Header Auth
auth_value_env = "N8N_WEBHOOK_KEY" # optional; secret via env
```
The webhook URL is the credential (Slack) — keep it in an env var, never in the
repo. n8n optionally needs a custom auth header (Header Auth recommended).

### Payloads
- **Slack**: top-level `text` (fallback, required) + `blocks` (header, a
  `section` with `fields` for status/verdict/phase/run id, divider, context
  footer). Success = HTTP 200, body `ok`.
- **n8n**: flat JSON — `source`, `event="run.completed"`, `phase`, `run_id`,
  `status`, `verdict`, `summary_path`, `summary_text` (short), `timestamp`.
  Success = any 2xx (default node returns `{"message":"Workflow got started"}`).

### CLI: `notify` subcommand (mirror the `show-clarity` pattern, `run_phase.py:1703`/`2240`/`2481`; add to `SUBCOMMANDS` at `run_phase.py:201`)
```
python studio/run_phase.py notify --run-dir output/studio/run_studio_... [--dry-run]
```
`--dry-run` prints the payloads without posting (useful for Block Kit preview).

### Auto-fire on finalize (optional, behind config)
After `write_json(meta_path, meta)` in `finalize_run` (`run_phase.py:1301`),
if `[slack].enabled`/`[n8n].enabled`, call `notify_run(run_dir, cfg)` inside a
try/except so a webhook failure only logs and never breaks finalize.

## Build order

Each step is independently verifiable; land them in this order.

1. **`studio/integrations/__init__.py` + `slack_digest.py`** — `post_json()`
   (urllib POST, 2xx=success, 429+Retry-After, never raises), `build_slack_blocks()`,
   `build_n8n_payload()`, `notify_run(run_dir, config)`.
   *Verify:* unit-test the payload builders; `import studio.integrations.slack_digest` clean.
2. **Config loader** for `.studio/integrations.toml` (reuse `persona_overrides.py:66`
   tomllib pattern); URLs/secrets resolved from env vars named in the toml.
   *Verify:* missing file → disabled no-op; env-var indirection resolves.
3. **`notify` subcommand** (`--run-dir`, `--dry-run`), mirroring `show-clarity`
   (parser `:1703`, handler `:2240`, dispatch `:2481`, `SUBCOMMANDS` `:201`).
   *Verify:* `--dry-run` prints both payloads for a seeded run.
4. **Auto-fire on finalize** behind `enabled` flags, after `write_json` at
   `run_phase.py:1301`, wrapped in try/except.
   *Verify:* simulated webhook failure logs but finalize still succeeds.
5. **`studio/tests/test_slack_digest.py`** with `urllib` mocked — payload build,
   success, HTTP error, timeout, 429 retry, disabled/no-config no-op.
   *Verify:* `cd studio && python -m pytest tests/ -v` green.
6. **Docs** — `CLAUDE.md` CLI list + short `studio/docs/INTEGRATIONS.md`.
   *Verify:* docs match shipped flags/behavior (MVI docs gate).

## Acceptance criteria

- [ ] `studio/integrations/__init__.py` + `slack_digest.py` exist; stdlib-only imports.
- [ ] `notify` subcommand prepares + posts digest for a finalized run; `--dry-run` prints payloads.
- [ ] Slack payload renders as a Block Kit digest (verified in Block Kit Builder).
- [ ] n8n payload is flat JSON addressable as `$json.body.<field>`; optional auth header sent when configured.
- [ ] Webhook failure / timeout / 429 is handled soft (logged, returns False, no exception escapes).
- [ ] No secret in repo: URL read from env var named in `.studio/integrations.toml`.
- [ ] `studio/tests/test_slack_digest.py` covers: payload build, success, HTTP error, timeout, 429 retry, disabled/no-config no-op — all with `urllib` mocked.
- [ ] Docs updated: `CLAUDE.md` CLI list + a short `studio/docs/INTEGRATIONS.md`.
- [ ] All existing tests still pass (`cd studio && python -m pytest tests/ -v`).

## References

- Slack Incoming Webhooks (payload, success/error bodies): https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks
- Slack Block Kit — header / section(fields) / context blocks: https://docs.slack.dev/reference/block-kit/blocks/section-block
- Slack rate limits (1/sec, 429 + Retry-After): https://docs.slack.dev/apis/web-api/rate-limits
- n8n Webhook node (URLs, methods, `$json.body`, auth, response): https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/
- n8n Webhook credentials (Header/Basic/JWT auth): https://docs.n8n.io/integrations/builtin/credentials/webhook/

## Codebase anchors

- `run.json` builder: `studio/run_phase.py:1097` (`_build_run_meta`)
- `finalize_run` + hook point: `studio/run_phase.py:1262`, write-back at `:1301`
- CLI subcommand pattern: parser `:1703`, handler `:2240`, dispatch `:2481`, `SUBCOMMANDS` `:201`
- TOML config pattern: `studio/persona_overrides.py:66`, `studio/cleanup.py:78`
- Test conventions + fixtures: `studio/tests/conftest.py` (`studio_root`, `make_finalize_args`)

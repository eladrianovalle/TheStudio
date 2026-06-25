# TICKET: Activate the n8n run-digest target

**Type:** Task (ops + verification) · **Component:** `studio/integrations/slack_digest.py` (n8n path) · **Priority:** P3
**Status:** Open · **Author:** Adriano Valle · **Date:** 2026-06-25
**Follows:** `TICKET-slack-n8n-digest.md` (code shipped, PR #21)

> **Decisions (locked):** n8n Webhook node uses **Header Auth** (`X-API-Key`), no instance
> stood up yet. Local config pre-wired in `studio/.studio/integrations.toml` `[n8n]` block,
> currently `enabled = false`.

## Summary

The n8n code path already shipped with PR #21 — `build_n8n_payload()`, the optional auth
header, and `notify_run()` all support n8n, and the `[n8n]` config block is wired (disabled).
What remains is **operational**: stand up an n8n instance, build the receiving workflow,
supply the secrets, flip the target on, and verify a live POST end to end. No application
code is required for basic activation; the follow-ups below are optional polish.

## Already done (PR #21)

- `studio/integrations/slack_digest.py` — `build_n8n_payload()` (flat JSON), optional
  `auth_header`/`auth_value_env` Header Auth, `notify_run()` posts to n8n when `[n8n].enabled`.
- `studio/.studio/integrations.toml` — `[n8n]` block present, `enabled = false`,
  `webhook_url_env = "N8N_WEBHOOK_URL"`, `auth_header = "X-API-Key"`,
  `auth_value_env = "N8N_WEBHOOK_KEY"`.
- Tests: `test_notify_run_posts_to_enabled_targets` asserts the n8n payload + `X-API-Key`
  header are sent. Dry-run preview confirmed the payload shape.

## Remaining work

### A. Stand up n8n + receiving workflow (n8n side)
1. Provision an n8n instance (cloud or self-hosted behind HTTPS).
2. New workflow → **Webhook** trigger node: HTTP method **POST**; note the **Production URL**
   (`https://<host>/webhook/<path>`).
3. Set node **Authentication = Header Auth**; create a Header Auth credential named
   **`X-API-Key`** with a secret value (this becomes `N8N_WEBHOOK_KEY`).
4. Add downstream fan-out nodes consuming `$json.body.*`
   (`verdict`, `phase`, `run_id`, `status`, `summary_text`, `timestamp`) — e.g. a Slack node,
   Gmail, or a DB insert.
5. **Activate** the workflow (production URL 404s while inactive).

### B. Activate locally (Studio side)
6. Export both secrets and persist in `~/.zshrc` (as done for Slack):
   `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_KEY`.
7. Flip `[n8n].enabled` → `true` in `studio/.studio/integrations.toml`.

### C. Verify end to end
8. `python studio/run_phase.py notify --run-dir <run> --artifact-root studio`
   → expect `n8n: ok (HTTP 200 ...)` and the workflow firing in n8n.
9. Confirm a real `finalize` auto-posts to both Slack and n8n.

### D. Optional follow-ups (only if needed)
- Add a "receiving workflow" example (node layout + sample `$json.body` mapping) to
  `studio/docs/INTEGRATIONS.md`.
- Consider stricter n8n success detection (currently any 2xx is success; n8n's default
  "Immediately" response returns `200 {"message":"Workflow got started"}`). Only worth it if
  a "Respond to Webhook" node returns a meaningful status to act on.

## Acceptance criteria

- [ ] n8n workflow active, Webhook node on Header Auth (`X-API-Key`).
- [ ] `N8N_WEBHOOK_URL` + `N8N_WEBHOOK_KEY` exported and persisted; `[n8n].enabled = true`.
- [ ] `notify` against a real run returns `n8n: ok` and the workflow runs in n8n.
- [ ] `finalize` auto-posts to both targets.
- [ ] (If touched) `INTEGRATIONS.md` updated; all tests still pass.

## References

- Local config: `studio/.studio/integrations.toml` (gitignored) — `[n8n]` block.
- Setup steps: `studio/docs/INTEGRATIONS.md`.
- n8n Webhook node: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/
- n8n Webhook credentials (Header Auth): https://docs.n8n.io/integrations/builtin/credentials/webhook/

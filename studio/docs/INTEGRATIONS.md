# Integrations: Slack / n8n run digests

Studio can post a short **run digest** (phase, run id, status, verdict, summary)
to an HTTP webhook when a run finishes. The same code targets either a **Slack
Incoming Webhook** directly or an **n8n Webhook node** (which can then fan out to
Slack, email, a database, etc.). Both are just "HTTP POST a JSON body to a URL".

Implementation: `studio/integrations/slack_digest.py` (stdlib `urllib` only).
Disabled by default; nothing is sent until you enable a target.

## Quick start

1. **Create a webhook URL.**
   - *Slack:* api.slack.com/apps → your app → **Incoming Webhooks** → *Add New
     Webhook to Workspace* → pick a channel → copy the
     `https://hooks.slack.com/services/T.../B.../...` URL.
   - *n8n:* add a **Webhook** trigger node, copy its **Production URL**
     (`https://<host>/webhook/<path>`), and activate the workflow.

2. **Put the URL in an environment variable** (it is a secret, never commit it):
   ```bash
   export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T000/B000/XXXX"
   ```

3. **Enable the target** in `.studio/integrations.toml`:
   ```toml
   [slack]
   enabled = true
   webhook_url_env = "SLACK_WEBHOOK_URL"   # env var name, not the URL itself

   [n8n]
   enabled = false
   webhook_url_env = "N8N_WEBHOOK_URL"
   auth_header = "X-API-Key"               # optional (n8n Header Auth)
   auth_value_env = "N8N_WEBHOOK_KEY"      # optional secret for that header
   ```

4. **Send a digest:**
   ```bash
   python studio/run_phase.py notify --run-dir output/design/run_design_... --dry-run  # preview
   python studio/run_phase.py notify --run-dir output/design/run_design_...            # post
   ```

## Auto-fire on finalize

When `[slack].enabled` or `[n8n].enabled` is true, `finalize` posts the digest
automatically after writing `run.json`. It is **soft-fail**: a webhook error is
printed but never breaks finalize. With no target enabled, finalize is unchanged.

## Payloads

- **Slack**: a Block Kit message with a header, a two-column field section
  (status / verdict / phase / run id), the run summary body (markdown converted
  to Slack `mrkdwn` and truncated to ~2700 chars), a pointer to the full final
  doc, and a context footer. A top-level `text` fallback is always included
  (required by Slack). The body prefers a short plain-language `digest.md` (or
  `summary_human.md`) when the run authored one, falling back to `summary.md`;
  the "Final doc" pointer always targets the full `summary.md`.
- **n8n**: flat JSON addressable downstream as `$json.body.<field>`:
  `source`, `event` (`"run.completed"`), `phase`, `run_id`, `status`,
  `verdict`, `iterations_run`, `summary_path`, `summary_text` (truncated),
  `timestamp`.

## Security

The webhook URL **is** the credential (especially for Slack, which has no separate
auth). Keep it in an environment variable or an untracked file; never commit it
or log it in full. If a Slack URL leaks, delete the webhook in the Slack app to
invalidate it. For n8n, prefer **Header Auth** and store the header value via
`auth_value_env`.

## References

- Slack Incoming Webhooks: https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks
- Slack Block Kit (section/header/context): https://docs.slack.dev/reference/block-kit/blocks/section-block
- n8n Webhook node: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/
- n8n Webhook credentials (auth): https://docs.n8n.io/integrations/builtin/credentials/webhook/

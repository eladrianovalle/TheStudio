# Studio ↔ Project Bridge Template

Copy this into every non-Studio repo that depends on the centralized agents. It keeps your AI assistant (and future contributors) anchored to the shared workflow so requests stay contextualized without re-explaining integration steps.

## 1. Purpose & Quick Summary
- **Project:** `<PROJECT_NAME>`: one-line elevator pitch.
- **Why this bridge exists:** e.g., “We rely on Studio agents for market/design stress tests without copying prompts across repos.”
- **Latest status link:** `<link to canonical roadmap/issue>` so agents can grab recency quickly.

## 2. Studio Location & Access
- Studio root: Set via `STUDIO_ROOT` environment variable (e.g., `export STUDIO_ROOT="/path/to/studio"`).
- All interactions happen through `python $STUDIO_ROOT/run_phase.py …` plus your AI assistant; there is no CLI runtime or API service.
- This repo’s commands should always reference absolute paths so the assistant can copy/paste safely.

## 3. Environment Expectations
- No API keys are required. The debate happens inside your AI assistant.
- Artifact roots depend on where you run commands:
  - From `<PROJECT_NAME>` repo (default): `<PROJECT_NAME>/.studio/output/{phase}/run_*`
  - From Studio repo: `$STUDIO_ROOT/output/{phase}/run_*`
  - Optional explicit override: `STUDIO_ARTIFACT_ROOT=/absolute/path/to/project`
- Reference absolute run paths when citing results inside `<PROJECT_NAME>` docs, tickets, or PRs.
- Ensure local contributors have permission to write to whichever artifact root is active.

## 4. Canonical Project Inputs
List the artifacts that count as **canon** for this project so Studio has the full picture. Update whenever the authoritative source moves.

| Canon doc | Why it matters | Last updated |
| --- | --- | --- |
| `docs/app-metadata.md` | Tagline, identifiers, store copy | 2025-12-20 |
| `docs/narrative-content-consolidation.md` | Story, overlays, prompts | 2025-12-15 |
| `…` | `…` | `…` |

## 5. Prompt Stub
Paste (and tweak) this whenever you ask your assistant to run Studio from this repo:
```
See docs/studio-bridge.md for integration context + canon.
Canon: <bullet list aligned with Section 4>.
Task: Run Studio <phase> on <brief summary>. Use role pack <pack_name> and overrides <+role/-role>. After `run_phase.py prepare`, echo the run folder path, save artifacts (e.g., advocate--design--01.md) inside it, and cite the summary in our docs when done.
```
Mandatory elements:
1. Mention this bridge doc so the assistant reloads it first.
2. Enumerate which canon snippets to include.
3. Provide a 2-3 bullet recap of the feature/question.
4. Specify the role pack/overrides (or explicitly say “use default pack”).
5. Tell the assistant where to echo the saved artifact path (helps future sessions jump straight in).

## 6. Command Shortcuts
Run these from **this** repo:
```bash
# Prepare instructions + run folder (studio example)
python $STUDIO_ROOT/run_phase.py \
  prepare --phase studio \
  --text "<objective>" \
  --role-pack studio_core \
  --budget "$0-20/mo" \
  --max-iterations 3

# Prepare (non-studio example)
python $STUDIO_ROOT/run_phase.py \
  prepare --phase design \
  --text "<objective>"

# Finalize after the assistant saves artifacts
python $STUDIO_ROOT/run_phase.py \
  finalize --phase <phase> \
  --run-id <run_id> \
  --status completed --verdict APPROVED --hours 0.8 --cost 0
```
If `STUDIO_ROOT` is set, the helper script reads it automatically; otherwise adjust the absolute path in these snippets.

## 7. Workflow Checklist
1. **Confirm canon**: skim Section 4 docs, summarize the slice relevant to this ask.
2. **Choose roles**: decide which role pack + overrides apply (or stick with defaults).
3. **Prepare**: run `run_phase.py prepare …` and capture the emitted `run_id`, instructions path, role menu, and artifact checklist.
4. **Execute**: follow the Advocate ↔ Contrarian loop per invited role, then run the Integrator duel (studio) or implementer checklist (other phases). Save artifacts to the provided run directory.
5. **Finalize**: run `run_phase.py finalize …` so the active artifact root index/log stay current (`<active_output_root>/index.md` + `<active_knowledge_root>/run_log.md`). Address any “missing role” warnings before calling the run complete.
6. **Reference back**: link the generated summary/implementation markdown inside `<PROJECT_NAME>` issues/notes for traceability.

## 8. Maintenance
- Update Studio path info if the repo moves or if `STUDIO_ROOT` changes.
- Keep the canon table fresh; stale references cause hallucinated guidance.
- Staying current is automatic: a SessionStart hook nudges you to run `/studio-update` when your
  installed Studio falls behind upstream (once per update, quiet otherwise). Turn it off with
  `studio update --no-hook` or an empty `.studio/update-check.off`; add `.studio/update-check.json`
  to `.gitignore`.
- Studio's specs and their evidence files under `.studio/specs/` are **tracked docs meant to be
  committed** — unlike `.studio/output/` and `.studio/knowledge/`, which must not be. If your
  `.gitignore` ignores `.studio/`, git will silently refuse to track them, and the obvious one-line
  fix does not work: git cannot re-include a file whose parent directory is excluded, so
  `!.studio/specs/` under a `.studio/` rule does nothing. Use this form instead:

  ```gitignore
  .studio/*
  !.studio/specs/
  ```

  Confirm with `git check-ignore -v .studio/specs/`.
- Record notable Studio runs at the bottom of this file (date, run_id, takeaway) so teammates can rehydrate context quickly.

---
Copy this template into each dependent repo as `docs/studio-bridge.md` (or similar). Fill in the placeholders so the assistant never loses the Studio ↔ project thread.

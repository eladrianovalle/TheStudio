# Studio ↔ Project Bridge Template

Copy this into every non-Studio repo that depends on the centralized agents. It keeps Cascade (and future contributors) anchored to the shared workflow so requests stay contextualized without re-explaining integration steps.

## 1. Purpose & Quick Summary
- **Project:** `<PROJECT_NAME>` – one-line elevator pitch.
- **Why this bridge exists:** e.g., “We rely on Studio agents for market/design stress tests without copying prompts across repos.”
- **Latest status link:** `<link to canonical roadmap/issue>` so agents can grab recency quickly.

## 2. Studio Location & Access
- Studio root: `/Users/orcpunk/Repos/_TheGameStudio/studio` (export `STUDIO_ROOT` if you keep it somewhere else).
- All interactions happen through `python $STUDIO_ROOT/run_phase.py …` plus Cascade chat; there is no CLI runtime or API service.
- This repo’s commands should always reference absolute paths so Cascade can copy/paste safely.

## 3. Environment Expectations
- No API keys are required—the debate happens inside Windsurf/Cascade.
- Runs always save artifacts under `$STUDIO_ROOT/output/{phase}/run_*`. Reference those absolute paths when citing results inside `<PROJECT_NAME>` docs, tickets, or PRs.
- Ensure local contributors have permission to write to the Studio repo (shared volume, git submodule, etc.).

## 4. Canonical Project Inputs
List the artifacts that count as **canon** for this project so Studio has the full picture. Update whenever the authoritative source moves.

| Canon doc | Why it matters | Last updated |
| --- | --- | --- |
| `docs/app-metadata.md` | Tagline, identifiers, store copy | 2025-12-20 |
| `docs/narrative-content-consolidation.md` | Story, overlays, prompts | 2025-12-15 |
| `…` | `…` | `…` |

## 5. Prompt Stub for Cascade
Paste (and tweak) this whenever you ask Cascade to run Studio from this repo:
```
See docs/studio-bridge.md for integration context + canon.
Canon: <bullet list aligned with Section 4>.
Task: Run Studio <phase> on <brief summary>. After `run_phase.py prepare`, echo the run folder path, save artifacts inside it, and cite the summary in our docs when done.
```
Mandatory elements:
1. Mention this bridge doc so Cascade reloads it first.
2. Enumerate which canon snippets to include.
3. Provide a 2–3 bullet recap of the feature/question.
4. Tell Cascade where to echo the saved artifact path (helps future sessions jump straight in).

## 6. Command Shortcuts
Run these from **this** repo (or via Windsurf command palette entries):
```bash
# Prepare instructions + run folder
python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
  prepare --phase <phase> --text "<idea or objective>" --max-iterations 3

# Finalize after Cascade saves artifacts
python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
  finalize --phase <phase> --run-id <run_id> --status completed --verdict APPROVED --hours 0.8 --cost 0
```
If `STUDIO_ROOT` is set, the helper script reads it automatically; otherwise adjust the absolute path in these snippets.

## 7. Workflow Checklist
1. **Confirm canon** – skim Section 4 docs, summarize the slice relevant to this ask.
2. **Prepare** – run `run_phase.py prepare …` and capture the emitted `run_id`, instructions path, and artifact checklist.
3. **Execute via Cascade** – follow the Advocate → Contrarian (→ Implementer/Integrator) loop, saving artifacts to the provided run directory.
4. **Finalize** – run `run_phase.py finalize …` so `output/index.md` + `knowledge/run_log.md` stay current.
5. **Reference back** – link the generated summary/implementation markdown inside `<PROJECT_NAME>` issues/notes for traceability.

## 8. Maintenance
- Update Studio path info if the repo moves or if `STUDIO_ROOT` changes.
- Keep the canon table fresh; stale references cause hallucinated guidance.
- Record notable Studio runs at the bottom of this file (date, run_id, takeaway) so teammates can rehydrate context quickly.

---
Copy this template into each dependent repo as `docs/studio-bridge.md` (or similar). Fill in the placeholders so Cascade never loses the Studio ↔ project thread.

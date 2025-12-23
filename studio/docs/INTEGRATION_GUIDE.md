# Integration Guide (Cascade-Only)

This doc explains how to integrate Studio into other repos now that the only supported workflow is: `run_phase.py` → Windsurf/Cascade chat → finalize/log. There is no importable Python API, CLI runtime, or hosted service. Treat Studio as a shared instructions generator plus artifact log.

---

## 1. Checklist for Every Repo

1. **Copy the bridge template**  
   - Copy [`docs/STUDIO_BRIDGE_TEMPLATE.md`](./STUDIO_BRIDGE_TEMPLATE.md) into your repo (e.g., `docs/studio-bridge.md`).  
   - Fill in Project summary, Studio location, canon table, and the Cascade prompt stub.
2. **Record Studio path**  
   - Prefer referencing `/Users/orcpunk/Repos/_TheGameStudio/studio`.  
   - If contributors keep it elsewhere, document how to set `STUDIO_ROOT`.
3. **Define canon**  
   - List the docs/data required for useful runs.  
   - Keep it updated so Cascade can reload context without guesswork.
4. **Decide where runs live**  
   - All artifacts live inside the Studio repo under `output/<phase>/run_*`.  
   - Link those artifacts back into your project issues/notes when citing them.

No other setup is required—Zero dependencies, zero API keys, zero services.

---

## 2. Integrating the Workflow

### Step A – Prepare from your repo

```bash
python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
  prepare --phase <market|design|tech|studio> \
  --text "Describe the idea or question" \
  --max-iterations 3
```

**Inputs you can override**

| Flag | Description |
| --- | --- |
| `--phase` | One of `market`, `design`, `tech`, `studio`. |
| `--text` | The prompt/brief you want evaluated. |
| `--budget` | Only used by the studio phase (default `$0-20/mo`). |
| `--max-iterations` | Advocate↔Contrarian loops (default 3). |

**Outputs (always absolute paths)**  
```
output/<phase>/run_<phase>_<timestamp>/
  instructions.md        # what to paste into Cascade
  run.json               # metadata
  (empty placeholders for advocate_*.md, etc.)
```

Capture the printed `run_id` and `instructions.md` path—your prompts to Cascade should reference them directly.

### Step B – Execute via Cascade

Use the prompt stub in your bridge doc. Remind Cascade to:
1. Read the bridge doc to understand canon + expectations.
2. Open the `instructions.md` file.
3. Save artifacts (`advocate_*.md`, `contrarian_*.md`, implementation/integrator, `summary.md`) in the run folder.
4. Tell you when it’s finished so you can run finalize.

### Step C – Finalize + log

```bash
python /Users/orcpunk/Repos/_TheGameStudio/studio/run_phase.py \
  finalize --phase <phase> \
  --run-id run_<phase>_<timestamp> \
  --status completed --verdict APPROVED \
  --hours 0.5 --cost 0
```

Finalize will fail with a checklist if required files are missing (see README). Once it passes, `output/index.md` and `knowledge/run_log.md` include this run and downstream teams can find it instantly.

---

## 3. Command Snippets You Can Copy into Other Repos

### `scripts/studio_prepare.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

STUDIO_ROOT="${STUDIO_ROOT:-/Users/orcpunk/Repos/_TheGameStudio/studio}"

python "$STUDIO_ROOT/run_phase.py" \
  prepare \
  --phase "${1:-market}" \
  --text "${2:-"Describe the objective"}" \
  --max-iterations "${3:-3}"
```

### `scripts/studio_finalize.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

STUDIO_ROOT="${STUDIO_ROOT:-/Users/orcpunk/Repos/_TheGameStudio/studio}"

python "$STUDIO_ROOT/run_phase.py" \
  finalize \
  --phase "${1:?phase required}" \
  --run-id "${2:?run_id required}" \
  --status "${3:-completed}" \
  --verdict "${4:-APPROVED}" \
  --hours "${5:-0.5}" \
  --cost "${6:-0}"
```

Commit these helpers to dependent repos if you want reproducible ergonomics; otherwise ask Cascade to run the commands directly.

---

## 4. Automation Ideas (Still Cascade-First)

| Need | Approach |
| --- | --- |
| Run Studio on every feature branch | Include “Prepare Studio run” in your PR checklist; attach run folder + summary link in PR template. |
| Slack/Teams share-outs | Link to `output/<phase>/run_*/summary.md`. Cascade can paste highlights into chat if you give it the path. |
| Command palette entries | Use the JSON snippet from `WINDSURF_USAGE.md` to register prepare/finalize commands so teammates don’t need shell access. |
| Rehydrating context | Add a section to each repo’s bridge doc summarizing recent run IDs and verdicts so Cascade can jump straight in. |

---

## 5. Troubleshooting Integration

| Problem | Fix |
| --- | --- |
| Team member doesn’t have Studio cloned | Add it as a git submodule or document a “clone + set STUDIO_ROOT” onboarding step. |
| Cascade forgets to save artifacts | Update the bridge prompt stub to explicitly say “save outputs to `<run_dir>/advocate_1.md` etc.” and remind Cascade after each iteration. |
| Run folders piling up | Use `output/index.md` to prune stale runs or create a clean-up task that archives old directories (never delete active ones). |
| Need a different expert voice | Add/override roles via `studio.manifest.json` in your repo and remind Cascade to read it. |

---

## 6. Reference Docs

- [README.md](../README.md) – top-level overview and testing notes.
- [STUDIO_INTERACTION_GUIDE.md](../STUDIO_INTERACTION_GUIDE.md) – the canonical user workflow.
- [WINDSURF_USAGE.md](./WINDSURF_USAGE.md) – conversational prompts + palette shortcuts.
- [API.md](./API.md) – command/JSON schema for `run_phase.py`, metadata, and logs.
- [STUDIO_BRIDGE_TEMPLATE.md](./STUDIO_BRIDGE_TEMPLATE.md) – copy/paste contract for every repo.

Keep these documents synchronized whenever the workflow changes—there is no hidden API anymore.

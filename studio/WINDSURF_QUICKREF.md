# Studio + Windsurf Quick Reference

## 🚀 One-Time Setup

- Set `STUDIO_ROOT` environment variable to your Studio path (e.g., `export STUDIO_ROOT="/path/to/studio"`).
- Copy the bridge template into each repo that uses Studio (`docs/studio-bridge.md`) and fill in canon + instructions.
- Optionally add a Windsurf command palette action for `run_phase.py prepare` (snippet in [WINDSURF_USAGE.md](./docs/WINDSURF_USAGE.md)).

No PATH edits or API keys are required—the models run inside Cascade.

## 💬 Standard Flow (per phase)

1. **Prepare** (from any terminal/repo):
   ```bash
   python $STUDIO_ROOT/run_phase.py \
     prepare --phase <market|design|tech|studio> \
     --text "Describe your idea or objective" \
     --max-iterations 3 \
     --role-pack studio_core \        # studio only, optional
     --roles +qa -marketing           # studio only, optional overrides
   ```
   Copy the emitted `run_id`, run directory, and instructions path.
2. **Cascade execution**:
   - Open Windsurf chat and paste the instructions.
   - Save each Advocate/Contrarian output to the provided files:
     - Non-studio → `advocate_<n>.md`, `contrarian_<n>.md`.
     - Studio → `advocate--<role>--<n>.md`, `contrarian--<role>--<n>.md` (per the Role Menu).
   - Produce `implementation.md` (non-studio) or run the integrator duel inside `integrator.md` (studio) once approved.
   - Summarize in `summary.md`.
3. **Finalize**:
   ```bash
   python $STUDIO_ROOT/run_phase.py \
     finalize --phase <phase> \
     --run-id <run_id> \
     --status completed --verdict APPROVED \
     --hours 0.8 --cost 0
   ```
   This enforces the artifact checklist and refreshes `output/index.md` + `knowledge/run_log.md`.

## 🎯 Quick Prompts for Cascade

- “Use Studio (market phase) on: **A 3D stealth horror roguelike**. Instructions in `output/market/run_market_…/instructions.md`.”
- “Run Studio design phase for **A puzzle platformer with portal mechanics**. Save artifacts to the prepared run folder, then summarize the verdict.”
- “Carry out Studio tech phase on **A multiplayer card battler**. After completion, remind me to run finalize.”
- “Self-critique Studio (studio phase). Use the manifest + bridge doc canon before responding.”

Always mention the bridge doc and run directory path so Cascade reloads the right context.

## 🗂️ Required Artifacts (per run)

| Phase | Files |
| --- | --- |
| Market/Design | `advocate_<n>.md`, `contrarian_<n>.md`, `summary.md` |
| Tech | `advocate_<n>.md`, `contrarian_<n>.md`, `implementation.md`, `summary.md` |
| Studio | `advocate--<role>--<n>.md`, `contrarian--<role>--<n>.md`, `integrator.md` (with Integrator duel sections), `summary.md` |

## 📖 More Detail

See [WINDSURF_USAGE.md](./docs/WINDSURF_USAGE.md) for deep-dive setup, sample prompts, and optional Windsurf shortcuts.

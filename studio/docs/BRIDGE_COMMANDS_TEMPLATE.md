# Bridge Slash Commands for External Repos

Copy the command files below into your repo's `.claude/commands/` directory to enable Studio slash commands from any project.

## Setup

```bash
mkdir -p .claude/commands
# Copy from Studio repo:
cp "$STUDIO_ROOT/docs/BRIDGE_COMMANDS_TEMPLATE.md" .  # This reference doc
```

Then create the two command files below.

## `.claude/commands/run-phase.md`

```markdown
# Studio Phase Run

Execute a structured advocate/contrarian debate via Studio.

## Arguments

- `$ARGUMENTS` — Required. Format: `--phase <market|design|tech> --text "your idea or objective"`
- Optional: `--max-iterations N` (default 3)

## Instructions

You are executing a Studio phase run from an external repo. Follow these steps exactly:

### Step 1: Prepare

```bash
python "$STUDIO_ROOT/run_phase.py" prepare $ARGUMENTS --no-scopes
```

Artifacts will land in this repo under `.studio/output/`. On first run, Studio will create the `.studio/` directory and a bridge doc at `docs/studio-bridge.md`.

Note the run_id and run directory path from the output.

### Step 2-6: Same as Studio repo

Follow the same advocate/contrarian/finalize flow. See the Studio repo's `.claude/commands/run-phase.md` for the full instructions.

Key: always use `python "$STUDIO_ROOT/run_phase.py"` instead of `cd studio && python run_phase.py`.
```

## `.claude/commands/run-studio-phase.md`

Same pattern: copy from the Studio repo's `.claude/commands/run-studio-phase.md` and replace all `cd studio && python run_phase.py` with `python "$STUDIO_ROOT/run_phase.py"`.

## Environment

Set `STUDIO_ROOT` in your shell profile or `.env`:

```bash
export STUDIO_ROOT="/absolute/path/to/TheGameStudio/studio"
```

Or add it to your repo's CLAUDE.md so Claude Code picks it up automatically.

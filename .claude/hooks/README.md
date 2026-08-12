# Claude Code hooks

Hooks kept here are tracked so they have a history and a home. Unlike `.claude/commands/` and
`.claude/workflows/`, **the installer does not ship them** — nothing in this directory reaches a
consuming repo. Installation is manual and machine-local.

## `finish-check.py`

A Stop hook that enforces the "finish the task" rule in `CLAUDE.md`: don't end a turn with work
you just described still undone. Instructions in `CLAUDE.md` are read *before* the work, while the
loose ends are still hypothetical. This fires *after* the message is written, when they are
concrete and countable.

It blocks the first stop of every turn with a short reason and lets the second through, so the
cost is one re-read per turn. Two guards keep it from looping: the `stop_hook_active` flag the
harness sets on a hook-caused stop, and a per-session marker file under `state/`.

### Installing it

It belongs in **global** settings (`~/.claude/settings.json`), not in a repo — a Stop hook is a
habit you want in every project, and registering it once covers all of them:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /Users/orcpunk/.claude/hooks/finish-check.py",
            "timeout": 10,
            "statusMessage": "Finish-check: anything left undone?"
          }
        ]
      }
    ]
  }
}
```

To keep this tracked copy as the live one rather than letting the two drift, point the global path
at it:

```bash
mkdir -p ~/.claude/hooks
ln -sf "$PWD/.claude/hooks/finish-check.py" ~/.claude/hooks/finish-check.py
```

Python resolves `__file__` to the path it was invoked by, so the log and `state/` markers still
land in `~/.claude/hooks/` and never touch this repo.

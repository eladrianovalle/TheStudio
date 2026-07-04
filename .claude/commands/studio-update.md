# Studio Update

Update this project's installed Studio source and slash commands from the upstream repo.

## Instructions

You are updating this project's Studio installation. Follow these steps:

### Step 1: Find the source

**Studio path:** Use `.studio/source/run_phase.py` for all commands below. If that file does not exist but `studio/run_phase.py` does, use `studio/run_phase.py` instead (you are in the Studio source repo).

If `.studio/VERSION` doesn't exist, tell the user: "Studio isn't installed in this project. Install it first from the Studio source repo."

### Step 2: Check for updates

```bash
python ".studio/source/run_phase.py" check-install --target .
```

If already up to date, tell the user and stop.

**If that command fails to run at all** — a Python traceback, `ModuleNotFoundError`, or
`ImportError` instead of a normal report — the installed snapshot is broken or too old to run
itself (a past install bug, or a snapshot predating a module that current code imports). **Do not
debug the traceback and do not try to fix the snapshot by hand.** Run the check and update from the
**upstream** Studio repo instead, pointing at this project — the upstream copy is current and its
`update` re-copies a working snapshot in, repairing it:

```bash
# The upstream repo path is recorded in this project's .studio/VERSION under "source_path".
python "<upstream>/studio/run_phase.py" check-install --target .
python "<upstream>/studio/run_phase.py" update --target .
```

Read `source_path` from `.studio/VERSION` to find `<upstream>`. If it's missing or the path no
longer exists, tell the user you need the path to their Studio source repo to recover. Use the
upstream entrypoint for Step 3 as well; skip the snapshot entrypoint entirely until the update has
repaired it.

**If the output contains a `WARNING:` line** (e.g. "running from the installed snapshot … cannot
compare against live source"), the check/update is running against the snapshot and cannot see the
real upstream, so it may report "up to date" when it isn't. In that case, tell the user to run the
update from the upstream Studio source repo instead:
`python studio/run_phase.py update --target <this-repo>`. Do not trust the result until then.

**If the output contains a `⚠️ … LOCAL EDITS` block** (installed snapshot files the user edited),
this is the clobber preview. **STOP and surface it to the user before updating.** `update` will
refuse to overwrite these unless `--force` is passed. For each listed file: if it's project config,
the fix is to move it to `<repo>/.studio/<name>.toml` (the project-override location update never
touches); otherwise confirm with the user whether to keep the edit (back it up) or discard it.

### Step 3: Update

```bash
python ".studio/source/run_phase.py" update --target .
```

If `update` prints `Update BLOCKED`, do NOT pass `--force` on your own; relay the listed files to
the user and let them decide (move config out, back up, or explicitly approve `--force`). Otherwise
show the user what was updated (files changed, added, removed).

### Step 4: Remind about restart

Tell the user: "Slash commands updated. Restart your session for changes to take effect."

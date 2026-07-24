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

**If the output contains a `WARNING:` line** (e.g. "running from the installed snapshot … cannot
compare against live source"), the check/update is running against the snapshot and cannot see the
real upstream, so it may report "up to date" when it isn't. In that case, tell the user to run the
update from the upstream Studio source repo instead:
`python studio/run_phase.py update --target <this-repo>`. Do not trust the result until then.

**If the output says the Studio source is behind its remote** (a "source is N commits behind
`origin/main`" block; `check-install` exits non-zero), the source repo Studio is comparing against
is itself out of date — its local `main` hasn't pulled. This is caught by a quick `git fetch` of
the source; `check-install` then compares against `origin/main` instead of the stale local tree, so
it won't report a false "up to date." `update` handles this for you: it reinstalls from `origin/main`
rather than no-opping. Either way, tell the user to run `git -C <source> pull` so their own source
checkout catches up (Studio never pulls it for them). Pass `--no-fetch` to skip this network check
when working offline.

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

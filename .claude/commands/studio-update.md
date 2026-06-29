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
real upstream — so it may report "up to date" when it isn't. In that case, tell the user to run the
update from the upstream Studio source repo instead:
`python studio/run_phase.py update --target <this-repo>`. Do not trust the result until then.

### Step 3: Update

```bash
python ".studio/source/run_phase.py" update --target .
```

Show the user what was updated (files changed, added, removed).

### Step 4: Remind about restart

Tell the user: "Slash commands updated. Restart your session for changes to take effect."

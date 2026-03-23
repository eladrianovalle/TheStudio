# Studio Update

Update this project's installed Studio source and slash commands from the upstream repo.

## Instructions

You are updating this project's Studio installation. Follow these steps:

### Step 1: Find the source

Read `.studio/VERSION` in this project to get the `source_path` (where Studio was installed from).

If `.studio/VERSION` doesn't exist, tell the user: "Studio isn't installed in this project. Run `python <studio_root>/run_phase.py init --target .` first."

### Step 2: Check for updates

```bash
python "<source_path>/run_phase.py" check-install --target .
```

If already up to date, tell the user and stop.

### Step 3: Update

```bash
python "<source_path>/run_phase.py" update --target .
```

Show the user what was updated (files changed, added, removed).

### Step 4: Remind about restart

Tell the user: "Slash commands updated. Restart your session for changes to take effect."

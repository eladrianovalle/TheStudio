# Working Files Guide

Quick reference for where to put files to avoid accidental commits.

## Directory Structure

```
_TheGameStudio/
├── .scratch/          # Temporary working files (NEVER COMMITTED)
├── .private/          # Sensitive data (NEVER COMMITTED)
├── studio/
│   ├── output/        # Studio run outputs (NEVER COMMITTED)
│   ├── knowledge/     # Personal notes (NEVER COMMITTED)
│   └── docs/          # Documentation (COMMITTED)
├── docs/              # Project docs (COMMITTED)
└── README.md          # Project readme (COMMITTED)
```

## Quick Rules

### ✅ Safe to Commit
- `docs/` — Documentation
- `studio/docs/` — Studio documentation
- Root `*.md` files — README, CHANGELOG, etc.
- Source code in appropriate directories

### ❌ Never Committed (Automatic)
- `.scratch/` — Temporary working files
- `.private/` — Sensitive data
- `studio/output/` — All Studio run outputs
- `studio/knowledge/` — Personal notes and run logs

## Common Workflows

### Working on Analysis
```bash
# Put it in .scratch/
vim .scratch/my-analysis.md
# Automatically ignored, won't be committed
```

### Storing Sensitive Data
```bash
# Put it in .private/
vim .private/api-keys.txt
# Automatically ignored, won't be committed
```

### Studio Runs
```bash
# Outputs go to studio/output/ automatically
python studio/run_phase.py prepare --phase tech --text "..."
# Everything in studio/output/ is automatically ignored
```

### Documentation
```bash
# Put it in docs/ or studio/docs/
vim docs/NEW_FEATURE.md
# Will be committed normally
```

## Verification

Check if a file would be ignored:
```bash
git check-ignore -v path/to/file.md
```

Check what's staged for commit:
```bash
git status
```

## Protection Layers

1. **Directory-based** — Entire directories excluded (`.scratch/`, `.private/`, `studio/output/`, `studio/knowledge/`)
2. **Pattern-based** — Sensitive patterns excluded (`*secret*`, `*credential*`, `*.env.local`)
3. **Git status** — Always check before committing

## What If I Accidentally Commit Something?

**Before pushing:**
```bash
# Remove from staging
git reset HEAD path/to/file.md

# Or amend the commit
git commit --amend
```

**After pushing:**
Contact repository maintainer for help with history cleanup.

## Questions?

See `.scratch/README.md` and `.private/README.md` for more details.

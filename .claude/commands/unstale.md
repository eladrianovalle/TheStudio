# Unstale: Align All Docs to Current Reality

Audit the entire project for stale documentation, outdated references, wrong counts, dead links, and missing coverage — then fix everything in one pass.

## Arguments

- `$ARGUMENTS` — Optional. Scope hint like `--focus docs` or `--focus memory` to narrow the audit. Default: everything.

## Instructions

You are performing a comprehensive staleness audit. The goal: every doc, README, changelog, memory file, code comment, and usage example in this project should reflect the **current** state of the codebase — not what was true three commits ago.

### Phase 1: Snapshot Current State

Gather ground truth before comparing anything. Run these in parallel:

1. **Test count** — `cd studio && python -m pytest tests/ -q --no-header 2>&1 | tail -1` to get the actual test count.
2. **Module inventory** — `ls studio/*.py | wc -l` and `ls studio/*.py` to get the current module list.
3. **CLI commands** — `python studio/run_phase.py --help` to get the current command list.
4. **Git log** — `git log --oneline -20` for recent changes that may not be reflected in docs.
5. **File tree** — `ls studio/docs/` and `ls .claude/commands/` for the full doc and command inventory.

### Phase 2: Parallel Audit

Launch **four** agents in parallel. Each agent audits a different category and returns a list of findings (file, line, what's stale, what it should say). Agents must **not edit files** — research only.

#### Agent 1: Documentation Audit

Check every `.md` file in `studio/docs/`, `README.md`, `CLAUDE.md`, and `CHANGELOG.md` for:

- **Wrong counts** — test counts, module counts, role counts that don't match Phase 1 snapshot
- **Dead references** — mentions of files, modules, functions, or CLI commands that no longer exist
- **Missing coverage** — features that exist in code but aren't documented anywhere
- **Stale examples** — usage examples with wrong flags, removed options, or outdated output
- **Broken internal links** — relative links to files that have moved or been deleted
- **Changelog gaps** — shipped features not recorded in CHANGELOG.md

#### Agent 2: Code Comment & Docstring Audit

Check all `.py` files in `studio/` for:

- **Stale docstrings** — function docstrings that describe old behavior or wrong parameters
- **TODO/FIXME/HACK comments** — are they still relevant or already resolved?
- **Outdated inline comments** — comments referencing old variable names, removed features, or prior architecture
- **Wrong module-level docstrings** — top-of-file descriptions that don't match current purpose

#### Agent 3: Memory & Plans Audit

Check all files in the memory directory and any `*_PLAN.md` / `*_GUIDE.md` files in the repo root for:

- **Stale project status** — plans marked "in progress" that shipped, wrong test counts, outdated module lists
- **Outdated memories** — memory files referencing features, patterns, or conventions that changed
- **Missing memories** — significant decisions or conventions from recent work that aren't captured
- **Dead plan items** — milestones or tasks in plan docs that are done but not marked complete

#### Agent 4: Cross-Reference Consistency

Check that these things agree with each other:

- `CLAUDE.md` CLI reference vs actual `--help` output vs `API.md` vs `README.md` CLI section
- Module descriptions in `CLAUDE.md` vs `ARCHITECTURE.md` vs `README.md` project structure
- Slash command files vs their documentation in `CLAUDE_CODE_USAGE.md`
- `run.json` schema in `API.md` vs `README.md` vs actual fields written by `run_phase.py`
- Role list in `README.md` vs `studio.manifest.json`

### Phase 3: Fix Everything

Aggregate all findings from the four agents. For each finding:

1. **Verify it** — confirm the finding is real (agents can have false positives)
2. **Fix it** — edit the file to reflect current reality
3. **Skip it** — if the finding is a false positive or cosmetic, note it and move on

Group related fixes into logical batches. Fix docs and code in the same pass — don't leave one stale while updating the other.

### Phase 4: Verify and Report

After all fixes:

1. Run `cd studio && python -m pytest tests/ -q --no-header` to confirm nothing broke
2. Summarize what was fixed, grouped by category:
   - **Counts updated** (test counts, module counts, etc.)
   - **Dead references removed**
   - **Missing docs added**
   - **Stale examples corrected**
   - **Memory files updated**
   - **Comments cleaned up**
3. Note anything that looks suspicious but you weren't confident enough to fix — flag these for the user

### Key Rules

- **Don't create new doc files** unless there's a clear gap (e.g., a major feature with zero documentation). Prefer updating existing files.
- **Don't rewrite docs for style** — only fix factual staleness. If a sentence is ugly but accurate, leave it.
- **Preserve historical accuracy** — changelog entries for old versions should reflect what was true *at that version*, not current state. Only update "current" sections.
- **Test counts must be exact** — run the tests, don't guess.
- **When in doubt, check the code** — the source is the ground truth, not the docs.

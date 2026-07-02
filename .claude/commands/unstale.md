# Unstale: Align All Docs to Current Reality

Audit the entire project for stale documentation, outdated references, wrong counts, dead links, and missing coverage, then fix everything in one pass.

This command is **stack-agnostic**. It detects what kind of project it's running in and audits *that* project's docs and code, whether it's a Rust crate, a Unity/C# game, a Node/TS app, or the Studio Python source itself. A project can pin exact commands and audit targets with an optional `.studio/unstale.toml` (schema at the bottom).

## Arguments

- `$ARGUMENTS`: Optional. Scope hint like `--focus docs` or `--focus memory` to narrow the audit. Default: everything.

## Instructions

You are performing a comprehensive staleness audit. The goal: every doc, README, changelog, memory file, code comment, and usage example in this project should reflect the **current** state of the codebase, not what was true three commits ago.

### Phase 0: Resolve Project Profile

Before auditing anything, figure out what project you're in and what commands describe its ground truth. This is what keeps the audit from chasing files that don't exist.

**1. Config override (preferred when present).** If `.studio/unstale.toml` exists, load it and use its values verbatim. Skip stack detection. Recognized keys (all optional):

- `[snapshot]` → `test_count`, `module_inventory`, `cli_help`: shell commands whose output is your ground truth.
- `[audit]` → `doc_globs`, `source_globs`, `cross_refs`: globs for docs/source to audit, and `cross_refs` (a list of "X should agree with Y" statements) for Agent 4.

Use whatever keys are present; fall back to detection (below) for anything the file omits.

**2. Stack self-detection (when no config, or to fill gaps).** Inspect well-known marker files in the project root and resolve a profile:

| Marker file(s) | Stack | `test_count` | `source_globs` |
|---|---|---|---|
| `studio/run_phase.py` or `.studio/source/run_phase.py` | **Studio source** | `python -m pytest tests/ -q --no-header 2>&1 \| tail -1` | `*.py` under the studio source dir |
| `Cargo.toml` | Rust | `cargo test 2>&1 \| tail -3` | `src/**/*.rs` |
| `*.csproj` or `ProjectSettings/` | Unity/C# | run via the Unity test runner if configured, else skip | `**/*.cs` (typically `Assets/Scripts/`) |
| `package.json` | Node/TS | read `scripts.test`, then run it (`npm test` / `pnpm test`) | `src/**/*.{ts,tsx,js}` |
| `pyproject.toml` / `setup.py` | Python | `python -m pytest -q --no-header 2>&1 \| tail -1` | `**/*.py` |
| `go.mod` | Go | `go test ./... 2>&1 \| tail -3` | `**/*.go` |
| *(none of the above)* | Generic | *(no test command, skip test-count checks)* | source files by dominant extension |

For `doc_globs`, default to `README.md`, `CHANGELOG.md`, `CLAUDE.md`, `AGENTS.md`, and everything under `docs/`, regardless of stack.

**3. Studio source repo.** If you detected the Studio source case, audit Studio precisely: modules are `.studio/source/*.py` (or `studio/*.py` in the source repo), CLI ground truth is `python <source>/run_phase.py --help`, and the role list comes from `studio.manifest.json`. The Studio-specific cross-references in Agent 4 apply only here.

**State the resolved profile** (stack, test command, source/doc globs, whether config was used) in one short block before continuing, so the user can see what's being audited.

### Phase 1: Snapshot Current State

Gather ground truth using the resolved profile. Run these in parallel:

1. **Test count:** run the profile's `test_count` command to get the actual count. Skip if the profile has none.
2. **Source inventory:** list files matching `source_globs` and count them, to spot module-count claims in docs.
3. **CLI / entrypoint surface:** if the project exposes a CLI (profile `cli_help`, e.g. `--help`), capture its current command list. Skip for projects with no CLI.
4. **Git log:** `git log --oneline -20` for recent changes that may not be reflected in docs.
5. **Doc & command tree:** list `doc_globs` files and `.claude/commands/` for the full doc and command inventory.
6. **Project tracking:** detect what tracking systems are in use. Check: is `gh` available and does the repo have a GitHub remote? Scan for local tracking patterns: `.tasks/`, `TODO.md`, `ISSUES.md`, `issues/`, `backlog/`, `.todo/`. Note which systems are active; Agent 5 needs this to decide whether to run.

### Phase 2: Parallel Audit

Launch **five** agents in parallel (skip Agent 5 if no tracking systems were found in step 6). Each agent audits a different category and returns a list of findings (file, line, what's stale, what it should say). Agents must **not edit files**. Research only. Each agent scopes its search to the profile's `doc_globs` / `source_globs`.

#### Agent 1: Documentation Audit

Check every doc matched by `doc_globs` (README, CHANGELOG, CLAUDE.md/AGENTS.md, everything under `docs/`) for:

- **Wrong counts:** test counts, module counts, role counts that don't match the Phase 1 snapshot
- **Dead references:** mentions of files, modules, functions, or CLI commands that no longer exist
- **Missing coverage:** features that exist in code but aren't documented anywhere
- **Stale examples:** usage examples with wrong flags, removed options, or outdated output
- **Broken internal links:** relative links to files that have moved or been deleted
- **Changelog gaps:** shipped features not recorded in the changelog

#### Agent 2: Code Comment & Docstring Audit

Check source files matched by `source_globs` for:

- **Stale doc comments:** function docstrings / doc comments (`///`, `/** */`, `"""`) that describe old behavior or wrong parameters
- **TODO/FIXME/HACK comments:** are they still relevant or already resolved?
- **Outdated inline comments:** comments referencing old variable names, removed features, or prior architecture
- **Wrong module/file-level headers:** top-of-file descriptions that don't match current purpose

#### Agent 3: Memory & Plans Audit

Check all files in the memory directory and any `*_PLAN.md` / `*_GUIDE.md` files in the repo root for:

- **Stale project status:** plans marked "in progress" that shipped, wrong test counts, outdated module lists
- **Outdated memories:** memory files referencing features, patterns, or conventions that changed
- **Missing memories:** significant decisions or conventions from recent work that aren't captured
- **Dead plan items:** milestones or tasks in plan docs that are done but not marked complete

#### Agent 4: Cross-Reference Consistency

Check that docs which state the same fact agree with each other. If the profile defines `cross_refs`, verify each listed pair. Otherwise, find facts asserted in more than one place and confirm they match. Common pairs:

- CLI reference in `CLAUDE.md` / `README.md` vs actual `--help` output vs any `API.md`
- Module / architecture descriptions across `CLAUDE.md`, `ARCHITECTURE.md`, and the README's project-structure section
- Slash command files vs their documentation
- Config schemas documented in one doc vs the fields the code actually reads/writes
- Any "list of things" (roles, commands, modules, phases) duplicated across docs

*Studio source repo only:* also check `CLAUDE.md` CLI vs `run_phase.py --help` vs `API.md`; module descriptions vs `ARCHITECTURE.md`; `run.json` schema across `API.md`/`README.md` vs what `run_phase.py` writes; role list in `README.md` vs `studio.manifest.json`.

#### Agent 5: Project Tracking Audit

Using the tracking systems detected in Phase 1 step 6, audit all open tracked items for staleness.

**For GitHub Issues** (if `gh` is available and repo is on GitHub):

- Issues referencing code, files, branches, or features that no longer exist in the repo
- Issues tied to PRs that have been merged but the issue was never closed
- Issues with stale status labels (e.g., "in progress" but the work already shipped)
- Duplicate issues: multiple issues tracking the same work
- Issues referencing branch names that have been deleted

**For local tracking files** (`.tasks/`, `TODO.md`, `ISSUES.md`, `issues/`, `backlog/`, `.todo/`, etc.):

- Items marked "in progress" or "open" whose work has already shipped (check git log, merged PRs, existing code)
- Items referencing files, modules, or features that were deleted or renamed
- Items tracking completed milestones or resolved TODOs
- Duplicate entries tracking the same work
- Orphaned tracking files that reference a context that no longer exists

### Phase 3: Fix Everything

Aggregate all findings from the five agents. For each finding:

1. **Verify it:** confirm the finding is real (agents can have false positives)
2. **Fix it:** edit the file to reflect current reality
3. **Skip it:** if the finding is a false positive or cosmetic, note it and move on

Group related fixes into logical batches. Fix docs and code in the same pass; don't leave one stale while updating the other.

**Special handling for Agent 5 (Project Tracking) findings:** group into two buckets: **safe to fix** (status text updates in local files, adding completion notes, minor wording corrections) and **needs your approval** (closing GitHub issues, deleting tracking files, removing entries, major edits). Apply safe items automatically. For approval-needed items, present the full list to the user with rationale and **wait for explicit confirmation** before proceeding. Do not batch these with other fixes; they require explicit sign-off.

### Phase 4: Verify and Report

After all fixes:

1. Re-run the profile's `test_count` command to confirm nothing broke (skip if the profile has no test command).
2. Summarize what was fixed, grouped by category:
   - **Counts updated** (test counts, module counts, etc.)
   - **Dead references removed**
   - **Missing docs added**
   - **Stale examples corrected**
   - **Memory files updated**
   - **Comments cleaned up**
   - **Tracking items fixed** (issues closed, local tracking updated; note which were auto-fixed vs user-approved)
3. Note anything that looks suspicious but you weren't confident enough to fix; flag these for the user

### Key Rules

- **Don't create new doc files** unless there's a clear gap (e.g., a major feature with zero documentation). Prefer updating existing files.
- **Don't rewrite docs for style:** only fix factual staleness. If a sentence is ugly but accurate, leave it.
- **Preserve historical accuracy:** changelog entries for old versions should reflect what was true *at that version*, not current state. Only update "current" sections.
- **Counts must be exact:** run the commands, don't guess.
- **When in doubt, check the code:** the source is the ground truth, not the docs.

### Config reference: `.studio/unstale.toml`

Optional. Pin exact commands and audit targets when self-detection isn't precise enough for your repo. Every key is optional; omitted keys fall back to stack detection.

```toml
[snapshot]
test_count       = "cargo test 2>&1 | tail -3"   # command whose output is the test ground truth
module_inventory = "fd -e rs . src | wc -l"      # command counting source modules
cli_help         = "cargo run -- --help"         # omit if the project has no CLI

[audit]
doc_globs    = ["README.md", "CHANGELOG.md", "docs/**/*.md"]
source_globs = ["src/**/*.rs"]
cross_refs   = [
  "README install steps vs docs/INSTALL.md",
  "CLI flags in README vs `--help` output",
]
```

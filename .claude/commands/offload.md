# Offload: Slim CLAUDE.md by Moving Reference Content to Companion Docs

Analyze CLAUDE.md for content that can be safely offloaded to companion documents, generate pointer stubs, and optionally apply the changes with full backup and rollback support.

## Arguments

- `$ARGUMENTS`: Optional flags:
  - `--apply`: After generating the report, prompt for approval and apply changes. Without this flag, /offload is read-only (report only).
  - `--rollback`: Restore from the most recent pre-apply backup.
  - `--verify`: Run canary verification on all offloaded docs (M3+).
  - `--dry-run`: (Default) Generate classification report without applying.

## Constraints

- This command targets Claude Code agents. Pointer patterns rely on the agent following Read directives.
- Canary tokens use exact string match only (`==`). Never use regex or substring matching for canary verification.
- In multi-turn sessions, a canary echo from a prior turn does not prove the agent re-read the doc in the current turn.

## Instructions

You are performing a structured analysis of CLAUDE.md to identify content that can be safely moved to companion documents while preserving agent behavior. The critical invariant: every instruction that shapes agent behavior must remain discoverable, either inline or via a pointer that reliably triggers a Read call.

### Phase 1: Snapshot

Gather ground truth before analysis. Run in parallel:

1. **Read CLAUDE.md:** full content, count lines, identify section boundaries (split on `## ` headers).
2. **Git status check:** if `--apply` flag is set, verify working tree is clean for all files that may be affected. Abort with explicit message if dirty.
3. **Cross-repo detection:** determine if running inside the Studio repo or a cross-repo install. Check (in order): `.studio/source/` directory, `studio/` directory (source repo), `CLAUDE.md` presence. After resolution, verify the companion doc root exists and is writable. Halt if not.
4. **Existing companion doc inventory:** list all `.md` files in `.studio/source/docs/`, `.studio/docs/`, and any paths referenced by CLAUDE.md.

### Phase 2: Parallel Analysis (3 agents)

Launch **three** agents in parallel. Each agent analyzes a different aspect and returns findings. Agents must **not edit files**. Research only.

#### Agent 1: Section Classifier

For each section in CLAUDE.md, assign a tier:

- **Always-inline:** Identity statements ("What This Is"), unconditional constraints with imperative language ("must", "never", "always"), conventions sections, and very short sections (<=5 lines) containing behavioral rules. These shape agent behavior from the first token of every session. Never offload.
- **Trigger-offloadable:** Content needed only during specific workflows (e.g., "Running a Studio Phase", relevant only when the agent is about to run a phase). Offload with a strong inline stub that names the trigger condition.
- **Reference-offloadable:** Lookup tables, CLI command catalogs, module inventories, configuration file lists, artifact structure descriptions. The agent consults these reactively. Safest to offload.

**Embedded constraint detection:** Scan trigger-offloadable and reference-offloadable sections for imperative language ("must", "never", "always", "required" as verbs, not adjectives). Flag any embedded constraint for manual review. It must either stay inline or be extracted into its own always-inline stub before the section can be offloaded.

For each section, report: name, line range, tier, embedded constraints found, reason for classification.

#### Agent 2: Pointer Pattern Generator

For each offloadable section, generate:

- **Trigger condition:** when the agent needs this content (e.g., "when running or modifying tests", "when navigating the module structure")
- **Inline stub:** the text that replaces the offloaded section in CLAUDE.md. Must use the strong pointer pattern: imperative verb + trigger condition + file path + consequence. Example:
  > **Before running or modifying CLI commands**, read `docs/CLI_REFERENCE.md` for the full command list and flags. Using wrong flags will produce misleading results.
- **Manifest table entry:** row for the top-of-file `## Offloaded References` table

**Score each pointer** using the strength rubric:
- Has imperative verb (read/check/review/consult): +0.3
- Has trigger condition (when/before/if + action): +0.4
- Has file path: +0.2
- Has consequence: +0.1
- Rating: >=0.7 "strong", >=0.5 "medium", <0.5 "weak"

**Weak pointers (score < 0.5) are P0 defects**: they must be rewritten to strong before any apply step. Do not proceed with a weak pointer.

#### Agent 3: Risk & Integration Scanner

- **Reconciliation:** Scan existing companion docs for structural overlap with content being offloaded. Use heading-level matching and explicit path references in CLAUDE.md. Recommend merge targets; do not create duplicate docs when an existing doc covers the same content.
- **Slash command scan:** Check all `.claude/commands/*.md` files for references to content being offloaded. Flag any command that would break or lose context if the content moves.
- **Canary plan:** For each companion doc (new or merged), generate a fresh `CANARY-<slug>-<hex8>` token. The token must NOT appear anywhere in CLAUDE.md or inline stubs; it lives only in the companion doc.

### Phase 3: Report

Aggregate findings from all three agents. Generate a structured report:

```
## /offload Classification Report
VALIDATION STATUS: PRE-RELEASE

### Summary
- Current CLAUDE.md: <N> lines
- Projected CLAUDE.md: <M> lines (<P>% reduction)
- Sections analyzed: <S>
- Always-inline: <A> | Trigger-offloadable: <T> | Reference-offloadable: <R>
- Embedded constraints flagged: <E>
- Weak pointers (P0 defects): <W>
- Existing doc merge targets: <G>
- Slash command conflicts: <C>

### Per-Section Classification
[Table: section name | tier | embedded constraints | pointer score | action]

### Pointer Stubs (Preview)
[For each offloadable section: the inline stub that would replace it]

### Manifest Table (Preview)
[The top-of-file ## Offloaded References table that would be added]

### Reconciliation Recommendations
[Merge targets with rationale]

### Conflicts & Warnings
[Slash command conflicts, embedded constraints needing review, weak pointers]
```

If `--apply` is not set, stop here. Print the report.

### Phase 4: Apply (only with --apply flag)

**Requires human approval.** Present the report, then ask:
> "Apply these changes? This will modify CLAUDE.md and create/update companion docs. A backup will be saved to `.studio/offload-backup/`. (y/n)"

If approved:

1. **Backup:** copy all affected files to `.studio/offload-backup/<timestamp>/`.
2. **Write companion docs:** create new docs or merge into existing ones. Append canary token at the end of each companion doc.
3. **Write manifest:** save `offload-manifest.json` to repo root (committed, not gitignored).
4. **Rewrite CLAUDE.md:** add `## Offloaded References` manifest table near the top, replace offloaded sections with inline stubs, keep all always-inline content untouched.
5. **Verify:** re-read CLAUDE.md and confirm: line count matches projection, zero canary tokens appear in CLAUDE.md, all companion docs exist and contain their canary tokens (exact string match).

If verification fails, automatically rollback from backup and report the failure.

### Phase 5: Canary Verification (--verify flag, M3+)

For each companion doc listed in `offload-manifest.json`:
1. Read the doc
2. Extract the expected canary token from the manifest
3. Check for exact string match (`==`) in the doc content
4. **Hard fail** for constraint-bearing docs (docs containing offloaded imperatives): recommend rollback
5. **Soft warning** for pure reference docs: log but continue

Report results with per-doc pass/fail status.

### Key Rules

- **Don't offload always-inline content:** identity, unconditional constraints, and conventions must stay in CLAUDE.md regardless of length.
- **Don't rewrite CLAUDE.md for style:** only move content that the classifier identifies as offloadable. Leave formatting, wording, and structure of remaining content untouched.
- **Embedded constraints must be resolved before offloading:** if a reference section contains imperative language, extract the constraint into an inline stub or keep the whole section. Never silently move a behavioral rule to a companion doc.
- **Weak pointers are blockers:** do not apply changes if any pointer scores below 0.5. Rewrite to strong first.
- **Reconcile before creating:** always check existing docs before creating new companion files. Merge into existing docs when there's structural overlap.
- **Canary tokens are exact-match only:** never use regex, substring, or fuzzy matching. The token either matches exactly or it doesn't.
- **The source code is ground truth:** when classifying sections, read the actual code to understand whether a description is a reference or a constraint.

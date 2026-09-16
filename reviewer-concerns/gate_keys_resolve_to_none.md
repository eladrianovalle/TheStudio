# Reviewer concerns — gate_keys_resolve_to_none

Two things raised in the editor pass. #1 is still open and is not a reason to hold the
unit; #2 is resolved.

## 1. Every installed repo without its own config file loses /forge until a sweep runs

**Concern.** The loader now says, of a repo with no file: `"there is no file at that
path."` and refuses. That is the point of the unit — but it changes the answer for repos
that were working. Detection used to hand a Python repo `pytest -q` and a Node repo
`npm test` with no file present at all; from here, a repo with no
`.studio/implementation_loop.toml` cannot run `/forge` at all. Memory says roughly half
the ten installs have never written one.

**Why unresolved.** Out of this unit's scope. Nothing in this worktree can write another
repository's config file, and the refusal is the behaviour the spec asked for.

**Follow-up.** Before this merges, run the cross-repo sweep and confirm each consumer has a
`.studio/implementation_loop.toml` with a real `test_command` — `/studio-setup` writes one,
and this change is exactly why it must have run everywhere first.

## 2. Nothing in the suite would notice if the committed gate config stopped being tracked

**Resolved.** `test_studios_own_gate_config_is_committed_and_loads` already runs
`git ls-files --error-unmatch` on the path and fails if the file is on disk but untracked,
skipping the check outside a git checkout. No follow-up needed.

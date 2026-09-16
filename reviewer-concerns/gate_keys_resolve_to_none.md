# Reviewer concerns — gate_keys_resolve_to_none

Two things I could not act on in the editor pass. Both are real; neither is a reason to
hold the unit.

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

**Concern.** `test_studios_own_gate_config_is_committed_and_loads` asserts
`own_config.is_file()`, which is true of any file sitting in the working tree — tracked or
not. What the acceptance criterion actually asks for is that `git ls-files
studio/.studio/implementation_loop.toml` returns it, and that depends on three `.gitignore`
lines in a specific order that the file's own comment calls out as fragile. I confirmed it
by hand; a future edit to those lines would untrack the file and leave the suite green.

**Why unresolved.** Out of this unit's scope: closing it means adding a test that shells out
to `git`, with a skip for a checkout that has no git — new machinery, which is not what an
editor pass is for.

**Follow-up.** Add one test that runs `git ls-files` on the path and asserts it comes back
non-empty, skipping when `git rev-parse --show-toplevel` fails.

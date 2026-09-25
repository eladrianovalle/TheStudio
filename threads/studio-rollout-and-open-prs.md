---
type: thread
status: active
slug: studio-rollout-and-open-prs
created: 2026-09-02
updated: 2026-09-15
---

# Studio: land the open PRs and get the static-check change to the consuming repos

## Goal
`specs/detected-static-check-command.md` reaches `status: shipped`. Unit 3 — the rollout to the two
consuming repos that carried a stale config — is built and measured; the spec flips when
`OrcPunk-biz` #19 and `cerebro` #226 merge. This thread's own Studio PRs are all merged;
TheStudio's one open PR, #175, belongs to the `studio-improvements-from-evidence` thread.

## Where this stands

**Done and verified (2026-09-02)**
- Main at `ed6b670`, clean, **992 tests passing**, `ruff` clean, 40/40 workflow shell tests.
- PR #143 merged: `static_checks` holds commands (`ruff check {paths}`), not tool names. A bare
  `ruff`/`eslint`/`mypy` is refused at load. Closed issue #131.
- PR #145 merged: rule 6 — an `approved` spec that promised evidence must carry a live
  `verification_due`, and the suite reds once it passes. Six rules now.
- PR #146 merged 2026-09-02: `specs/verification-due-date.md` is `shipped`.
- `detected-static-check-command` remains at `approved`, its unit 3 undone.

**In flight (verified 2026-09-13)**
- **Studio has zero open PRs.** Main at `eeea628`, 1020 tests, ruff clean. Merged since the last
  update of this note: #162 #163 #164 #165 #166.
- **Unit 3 is built and measured; it is waiting on two merges, not on work.** `OrcPunk-biz` #19 and
  `cerebro` #226 carry the rollout. All three of unit 3's acceptance criteria are met — criterion 2
  was narrowed in #166 to "neither raises the stale-config refusal", with the original wording quoted
  in the spec, because `OrcPunk-biz` has no tests and no stack marker and so raises on
  `gate.test_command` no matter what any update does.
- **The spec flips to `shipped` the moment those two merge.** Nothing else gates it; it carries no
  `## Verification` section, so no evidence file is owed.
- **The armed trap is gone from both repos.** Neither `_Cerebro` nor `OrcPunk-biz` still carries
  `static_checks = ["ruff"]`, and both now have the refusal installed. Re-measured 2026-09-12 by
  loading each repo's config: `_Cerebro` gives `['ruff check {paths}']`, `_Alfred` `['make lint']`,
  `Orkid Garden` `[]`.
- **`_Cerebro` was never actually blocked.** Its `.studio/source/` is gitignored while
  `MANIFEST.json` and `VERSION` are tracked, so the snapshot moved while the record of it stayed put
  and `check-install` reported 17 phantom "local edits". Every flagged file was byte-identical to its
  install. #226 regenerates the record; its stale #224 and #225 are closed as superseded.
- **The cross-repo sweep is done** (2026-09-13). Every consumer is current or has exactly one open PR
  that makes it so: `_Alfred` #270, `cerebro` #226, `cemetery-security` #721, `Multica`/orc-review
  #102, `OrcPunk-biz` #19, `OrcPunk-dotcom` #82. `miresu` needed no PR — its `CLAUDE.md` is
  gitignored, so its snapshot was delivered in place. `Orkid Garden` was already current.

## Decisions made
- **The rollout is a spec unit, not a follow-up issue.** Added as unit 3 of
  `specs/detected-static-check-command.md`, following the precedent of #122 — a rule that lands red
  on real data has not shipped, it has broken.
- **The backfill lives inside the unit that needs it.** `find-before-you-grep` got its
  `verification_due` in the same unit as rule 6, so the rule shipped with the repo green.
- **Rule 6b deliberately ignores `FILL_ME`.** A spec past due with *filled* evidence is a feature that
  did the work and forgot to flip its status — the case most worth catching. A writer docstring got
  this backwards once already; do not "fix" it.
- **`npm run lint` gets no `{paths}`.** Appending files to a script that names its own target widens
  the run. There is a comment beside it saying so.
- **`check-install` reports orphans, never prunes them.** The broad rule ("flag everything Studio
  doesn't ship") would sweep up the project's own hand-written commands.

## Blocked on
- **Adriano — merge `OrcPunk-biz` #19 and `cerebro` #226.** That is the whole remaining path to
  `shipped`. The other four sweep PRs are independent and can go in any order.
- **Adriano — issue #133.** Unchanged and still a decision rather than work: concern 1 shipped in
  #139 and the issue's own suggested fix was rejected on merit; concern 2 is fully intact at
  `studio/setup.py:721` and `:949`. Narrow the body to concern 2. Do not close it. The evidence
  comment is already posted.

## Landmines

- **The armed trap is defused** (2026-09-12); it is kept here only so nobody re-arms it. It worked
  like this: the refusal and the stale config had to arrive in either order, and the wrong order
  broke `/forge`. Studio's shipped `studio/config/implementation_loop.toml` names no gate keys, so an
  update clears the config in the same pass that delivers the refusal — which is why a plain update
  was always the fix and hand-editing never was.
- **A gitignored snapshot beside a tracked checksum file drifts silently**, and the drift reports
  itself as "someone hand-edited Studio's files". Diff the flagged files against the commit that
  installed them before believing it. This cost `_Cerebro` a month of stuck PRs.
- **Studio's shipped loop config is `studio/config/implementation_loop.toml`**, not `config/` at the
  repo root. Checking the wrong path returns "file missing" and looks like a different problem.
- **Do not park a feature branch in the main checkout.** Consuming repos read Studio from this working
  tree, so WIP leaks into their `/studio-update`. Use the worktree.
- **A spec that waits accumulates false premises.** `verification-due-date` sat three weeks and grew
  three: a taken rule number, a design move that had already shipped, and a claim that nothing needed
  backfilling. Re-check a waiting spec's named symbols against the tree before forging it.
- **Subagents dispatched into `_Alfred` must be told `Vault/Private/` is off-limits.** It is decrypted
  and plaintext at rest on this machine; the encryption protects the remote only.
- **`_Alfred` cannot take a plain worktree.** `git worktree add` dies with
  `smudge filter git-crypt failed` before checking anything out, because a worktree has no key. Use
  a sparse checkout that never materialises the vault: `git worktree add --no-checkout`, then
  `git sparse-checkout init --no-cone`, `git sparse-checkout set '/*' '!/Vault/'`, then `git checkout`.
- **Seeding a worktree's `.studio/` with `cp -R` silently no-ops** when the repo tracks any file
  under `.studio/`, because the destination already exists — `update` then says "Studio not
  installed". Copy the pieces (`source`, `VERSION`, `MANIFEST.json`), not the directory.

## Files & artifacts
- Repo: this checkout, main `eeea628`.
- Worktree: `../_TheGameStudio-wt-static-checks` (branch `chore/unstale-2026-09-02`).
  Keep it — `.studio/output/impl_loop/` handoff records are gitignored and die with the worktree.
- Spec: `specs/detected-static-check-command.md` — all three unit 3 criteria met, `approved` until
  the two rollout PRs merge.
- Open PRs, all mine, all ready: `OrcPunk-biz` #19, `cerebro` #226, `OrcPunk-dotcom` #82,
  `cemetery-security` #721. `_Alfred` #270 and `Multica`/orc-review #102 merged 2026-09-14.
  TheStudio's only open PR is #175, which belongs to the `studio-improvements-from-evidence`
  thread; #172 merged 2026-09-15.
  `cerebro` #224 and #225 are closed as superseded by #226.
- Issue: #133 (open, half-stale, comment posted).

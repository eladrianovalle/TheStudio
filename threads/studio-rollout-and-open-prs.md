---
type: thread
status: active
slug: studio-rollout-and-open-prs
created: 2026-09-02
updated: 2026-09-10
---

# Studio: land the open PRs and get the static-check change to the consuming repos

## Goal
`specs/detected-static-check-command.md` reaches `status: shipped` — which needs its unit 3, the
rollout to the two consuming repos still carrying a stale config — and Studio's open PRs are merged.

## Where this stands

**Done and verified (2026-09-02)**
- Main at `ed6b670`, clean, **992 tests passing**, `ruff` clean, 40/40 workflow shell tests.
- PR #143 merged: `static_checks` holds commands (`ruff check {paths}`), not tool names. A bare
  `ruff`/`eslint`/`mypy` is refused at load. Closed issue #131.
- PR #145 merged: rule 6 — an `approved` spec that promised evidence must carry a live
  `verification_due`, and the suite reds once it passes. Six rules now.
- PR #146 merged 2026-09-02: `specs/verification-due-date.md` is `shipped`.
- `detected-static-check-command` remains at `approved`, its unit 3 undone.

**In flight (verified 2026-09-10)**
- **Studio has zero open PRs.** Main at `660e806`, 1020 tests, ruff clean. Everything the old
  version of this note listed as in-flight has merged: #143 #145 #146 #147 #148 #149 #150 #151 #152
  #153 #154 #155 #156 #158 #159 #160. #157 is the one that did not: closed unmerged, folded into #154
  because a thread note belongs in the PR that carries the work it describes.
- **Unit 3 (the consumer rollout) is the only thing left, and the trap is still armed.** Re-checked
  today: `OrcPunk-biz` and `_Cerebro` both still load `static_checks = ['ruff']` — they load rather
  than refuse only because their installed Studio predates the refusal. **Their next `update`
  delivers the refusal alongside the stale config and breaks `/forge` in both.** The shipped config
  names no gate keys, so the update itself clears it — the update just has to happen.
- **`_Cerebro` is the expensive one.** Twelve of its installed files have drifted from the SHAs
  recorded at install, so `update` returns BLOCKED and only `--force` gets through, overwriting all
  twelve. Clearing it means reviewing those edits first, not running a command.
- `find-before-you-grep` is **shipped** (2026-09-04) on real evidence; that fuse is gone.

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
- **Adriano — issue #133.** Its body is half-wrong: concern 1 (the wizard wrote its config where
  `/forge` never read it) shipped in PR #139, and the issue's own suggested fix was rejected on merit.
  Concern 2 (a wizard-written file is indistinguishable from a hand-written one) is fully intact at
  `studio/setup.py:721` and `:949`. A status comment with the evidence is posted. **He needs to say
  whether to narrow the issue body to concern 2.** Do not close it.
- **Adriano — `_Cerebro` PRs #224 and #225.** 185 commits behind; nothing Studio-related can reach
  that repo until they merge. An earlier attempt to merge them was refused by the permission
  classifier, and that refusal was not routed around.
- **Adriano — two consumer PRs that should merge.** `OrcPunk-biz` #19 (it *deletes* the stale
  `static_checks = ["ruff"]` line, so merging it defuses the trap below) and `OrcPunk-dotcom` #82
  (verified 2026-09-01: the §5 draft-vs-ready text it carries is genuinely absent from that repo).

## Landmines

- **Armed trap, verified still armed on 2026-09-10.** `_Cerebro` and `OrcPunk-biz` both carry
  `static_checks = ["ruff"]` in `.studio/source/config/implementation_loop.toml`, and neither has the
  refusal installed yet (`grep -c LEGACY_STATIC_CHECK` returns 0 in both). **Nothing is broken today.**
  They break on the *next* `update`, which delivers the refusal alongside the stale config. Fix the
  config in the same pass — Studio's shipped `studio/config/implementation_loop.toml` names no gate
  keys, so the update alone clears it.
- **Studio's shipped loop config is `studio/config/implementation_loop.toml`**, not `config/` at the
  repo root. Checking the wrong path returns "file missing" and looks like a different problem.
- **Do not park a feature branch in the main checkout.** Consuming repos read Studio from this working
  tree, so WIP leaks into their `/studio-update`. Use the worktree.
- **A spec that waits accumulates false premises.** `verification-due-date` sat three weeks and grew
  three: a taken rule number, a design move that had already shipped, and a claim that nothing needed
  backfilling. Re-check a waiting spec's named symbols against the tree before forging it.
- **Subagents dispatched into `_Alfred` must be told `Vault/Private/` is off-limits.** It is decrypted
  and plaintext at rest on this machine; the encryption protects the remote only.

## Files & artifacts
- Repo: `/Users/orcpunk/Repos/_TheGameStudio`, main `660e806`.
- Worktree: `/Users/orcpunk/Repos/_TheGameStudio-wt-static-checks` (branch `chore/unstale-2026-09-02`).
  Keep it — `.studio/output/impl_loop/` handoff records are gitignored and die with the worktree.
- Specs: `specs/detected-static-check-command.md` (unit 3 pending).
- Open: `_Cerebro` #224/#225, `OrcPunk-biz` #19, `OrcPunk-dotcom` #82. TheStudio has none.
- Issue: #133 (open, half-stale, comment posted).

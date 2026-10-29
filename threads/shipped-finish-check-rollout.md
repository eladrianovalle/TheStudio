---
type: thread
status: active
slug: shipped-finish-check-rollout
created: 2026-09-29
updated: 2026-10-29
---

# Ship the finish-check Stop hook to every install

## Goal
Every Studio install gets the finish-check hook, and `specs/shipped-finish-check.md` reaches
`status: shipped`. Both are done as of 2026-10-29; what is left is the merge and two consumer pulls.

## Where this stands

**Done and verified (2026-10-29).**
- Spec (#210, #211), unit 1 (#213), unit 2 (#215), comment rule (#214): all merged.
- **All eleven installs carry the hook registration** (sweep 2026-09-29). Nine have the hardened
  script on disk. Cerebro #228 and OrcPunk-biz #22 are the only `chore/studio-finish-check-hook`
  pull requests still open; until merged and pulled they run an inert no-op hook, by design.
- **The evidence exists and the spec is flipped to `shipped`** on branch
  `chore/ship-finish-check-spec`. The instrument was never actually cut: Claude Code's transcripts
  under `~/.claude/projects/` record every blocked stop as a hook-feedback record. New module
  `studio/finish_check_tally.py` (+ `tests/test_finish_check_tally.py`) grades the turn after each
  block. Measured 1,048 blocks outside Studio since 2026-09-29; 401 followed by a concrete change,
  563 by nothing; 866 of 1,019 windows of 30 meet the 8-of-30 bar (first 13, latest 10, worst 3).
  Suite green on the branch: 1396 passed, ruff clean.
- `main` is `59a60d0` and red on rule 6 until that branch merges.

**Blocked downstream of the red suite: Studio PR #232** (`fix/installer-names-missing-listed-files`).
The reviewer REJECTED at `909888d`; the responder prepared the fix (comment and docstring reworded
to "listed but absent", `studio-update.md` exception, warning no longer prints a temp path) but
pushed nothing because the suite was red. Its three edits are spelled out in its comment on #232.
`origin/fix/installer-names-missing-listed-files` is still at `909888d`.

**Next action.** Once `chore/ship-finish-check-spec` merges: re-apply the responder's three edits
on #232 by hand from its comment, push, edit the PR body as the comment suggests, and open the
follow-up issue for the real Tycho case ("present in source, unlisted by an older installer": read
`SOURCE_FILES` from the source tree's own `install.py`, or run the update with the source's
installer). Then the OrcPunk-dotcom correction: its `CLAUDE.md` still carries the superseded
multi-line comment principle; re-splice the marker block from Studio `main` the way Multica #159 did.

## Decisions made

- **The hook blocks on every turn, not on evidence of deferral.** `last_assistant_message` is on
  every payload and deliberately unread; the model re-reading its own message is the better judge.
- **On by default, not a wizard step.** 3 of 11 installs have no `SETUP.json`; opt-in ships nowhere.
- **`finish_check.py` is copied but NOT in `SOURCE_FILES`.** Manifest membership is what the
  clobber guard reads; a guarded hook freezes that repo's whole update stream on one local edit.
  The sanctioned edit surface is `.studio/finish-check.txt`.
- **The payload log is cut, and stays cut.** Claude Code's transcripts already hold every blocked
  stop; `finish_check_tally.py` reads them. The hook never needs to log anything.
- **#232's skip stays a skip.** Stand-in trees in tests and a rolled-back source are legitimate; it
  warns, it does not refuse.

## Blocked on

- **Adriano: merge the spec-ship PR** from `chore/ship-finish-check-spec`. That unreds `main`.
- **Adriano: merge Cerebro #228 and OrcPunk-biz #22**, then pull each into its live checkout.
- **OrcPunk-dotcom's correction**, not yet opened (see Next action).

## Landmines

- **The registration can never travel in a pull request.** `_merge_hook_entry` writes
  `.claude/settings.local.json`, gitignored everywhere, because the command names an absolute
  interpreter path. Every install needs a run against its live checkout.
- **`/studio-update` runs the *installed* installer**, so a file added upstream to `SOURCE_FILES`
  is invisible to the update that would have fetched it. Tycho #69 lost `docs/DESIGN_LEDGER.md` this
  way, with `VERSION` claiming the full commit. The fix is to run the update again once the new
  installer is in place, or from the source repo. #232's warning does **not** catch this case.
- **A responder will not push onto a red suite**, even when the red is unrelated and on `main`. A
  date-expired spec therefore stalls every open PR's follow-up, not just its own.
- **Alfred's `Owns:` fork is live on `master`.** Its local checkout is far behind on a stale branch;
  `check-install` there passes and means nothing. Issue #207 is the real fix.
- **Always pull before believing a drift report.** Cerebro and Tycho were once written up as
  "behind" when their merged update PRs simply had not been pulled.
- **A branch switch takes the snapshot back with it** in a repo whose `.studio/` is tracked. Do not
  hand-copy the script back; the merge would refuse to overwrite an untracked file.
- **`/forge --work-dir` loses the handoff records** (gitignored `.studio/output/impl_loop/`).
  Copy them out before `git worktree remove`.
- **A stale `.git/index.lock` blocks everything silently.** One from 2026-10-26 sat in the main
  checkout with no git process alive; `rm` it after checking `pgrep -fl git`.
- **`_Alfred` cannot take a plain worktree** (git-crypt smudge fails). Use `--no-checkout` plus a
  sparse checkout excluding `/Vault/`. Tell any subagent `Vault/Private/` is off-limits.
- **Seeding a worktree's `.studio/` with `cp -R` silently no-ops** when the repo tracks anything
  under `.studio/`. Copy `source`, `VERSION` and `MANIFEST.json` individually.
- **The finish-check's own failure mode is silence.** A Stop hook that cannot start is let through.

## Files & artifacts

- Spec: `specs/shipped-finish-check.md` (`shipped` on the branch), evidence
  `specs/shipped-finish-check-eval-results.md` (filled from `studio/finish_check_tally.py`).
- Code: `studio/finish_check.py`; `_install_stop_hook` in `studio/install.py`; `--no-finish-check`
  in `studio/run_phase.py`. Tests: `studio/tests/test_finish_check.py`, `test_hook_install.py`.
- Open Studio PRs: the spec-ship PR (branch `chore/ship-finish-check-spec`), #232 (installer warning,
  rejected, patch unpushed), #227 (`/tend-prs` spec, worktree `_TheGameStudio-tend-prs`).
- Consumer PRs still open: Cerebro #228, OrcPunk-biz #22. Tycho #69 merged.
- Obligation queue also names `specs/game-design-board.md`: every unit built, still `approved`,
  owes a flip to `shipped` with `shipped_impact` and `shipped_changed`. Separate thread
  (`threads/game-design-boards.md`).
- Open issues: #207, #198, #181, #180. None blocks a consumer.

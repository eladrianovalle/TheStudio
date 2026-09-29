---
type: thread
status: active
slug: shipped-finish-check-rollout
created: 2026-09-29
updated: 2026-09-29
---

# Ship the finish-check Stop hook to every install

## Goal
Every Studio install gets the finish-check hook on its next `/studio-update`, so a session on any
machine — not just the one it was hand-wired on — is refused its first stop while work nothing is
blocking sits undone. Done when the eleven installs carry it and
`specs/shipped-finish-check.md` reaches `status: shipped`, which costs the evidence file.

## Where this stands

**Done and verified.**
- Spec merged (#210), approved with its evidence file opened empty (#211).
- Unit 1 merged (#213): `studio/finish_check.py`, hardened. `.claude/hooks/finish-check.py` retired.
- Unit 2 merged (#215): `_install_stop_hook`, `--no-finish-check`, the `.studio/finish-check.off`
  sentinel, docs in four files, and the pointer in `obligation-queue.md`'s Non-Goal.
- The comment rule that two downstream reviewers had to teach us is in the shipped coding
  principles (#214), so it reaches every install's `CLAUDE.md`.
- `main` is `8a16a4a`, clean, **no open Studio PRs besides this handoff**, suite 1359, `ruff check .` clean.
- The obligation queue reports **nothing owed**.
- `~/.claude/hooks/finish-check.py` was repointed at `studio/finish_check.py` and verified live
  (first stop refused with the paragraph intact, second allowed).

**In flight.** Nothing is running. No worktrees beyond the main checkout.

**Next action.** Roll the update out to the installs — and **step one is removing the global `Stop`
registration** in `~/.claude/settings.json`, which still reads
`python3 /Users/orcpunk/.claude/hooks/finish-check.py`. Leave it and every repo fires the hook twice
per stop: two processes racing one marker, one writing it while the other reads it fresh and deletes
it. The installer cannot detect it — the registered path has a hyphen, the shipped one an underscore.
After that, sweep per `project_cross_repo_push_procedure`.

## Decisions made

- **The hook blocks on every turn, not on evidence of deferral.** A keyword matcher deciding when a
  turn is finished is a worse judge than the model re-reading its own message. `last_assistant_message`
  is present on every payload and deliberately unread.
- **On by default, not an opt-in wizard step.** 3 of 11 installs have no `SETUP.json` at all, and
  wizard v5's five runs were mostly one scripted minute. Opt-in ships a feature enabled nowhere.
- **`finish_check.py` is copied into `.studio/source/` but deliberately NOT in `SOURCE_FILES`.**
  Manifest membership is what the clobber guard reads; a guarded hook means one local edit freezes
  that repo's entire update stream. Unguarded means `update` overwrites it every run. The sanctioned
  edit surface is `.studio/finish-check.txt`, which Studio never writes.
- **The payload log is cut.** It held whole assistant turns and measured a ratio the design
  guarantees.
- **Criterion 3 of unit 2 was narrowed after measuring**, with the original quoted below the Build
  Plan. It had asked the wrong installer to be still.

## Blocked on

- **Adriano, to start the rollout** — and to remove that global registration first.
- **The evidence file**, `specs/shipped-finish-check-eval-results.md`, still four `FILL_ME`s.
  `verification_due: 2026-10-28`; once that passes with it blank the suite goes red. The spec stays
  `approved` until it is filled. Pass criterion: across 30 consecutive blocked stops outside this
  repo, at least 8 produce a concrete change in the following turn.

## Landmines

- **`_Alfred` is no longer blocked.** Its `Owns:` fork of `.claude/commands/spec.md` is gone and the
  file matches its recorded checksum, so a plain `update` works — **no `--force` needed**. Issue #207
  (upstreaming the `Owns:` convention) is still open on its merits, not as a blocker.
- **Two local checkouts are stale, not behind.** `_Cerebro` and `Tycho` have merged update PRs their
  working copies have not pulled, so `check-install` reports drift that a `git pull` clears. Always
  pull before believing a drift report.
- **`/forge --work-dir` loses the handoff records.** The loop writes them to the worktree's gitignored
  `.studio/output/impl_loop/<unit_id>/`, so `git worktree remove` takes them. `reviewer-concerns/`
  survives because it is deliberately tracked. Copy the handoffs out first.
- **Without `--work-dir`, a pr-gate responder can move the branch under the loop.** That happened on
  unit 1: the writer and editor commits landed on an unrelated open PR's branch. Repair is a
  cherry-pick onto the right base plus `git branch -f <other> origin/<other>`.
- **The evidence file's skeleton is pinned.** While `## What happened` says `FILL_ME`, every line of
  that section must match what `/spec` prints — table rows and guidance prose both. Put anything
  feature-specific in the spec's Verification section instead.
- **Subagents dispatched into `_Alfred` must be told `Vault/Private/` is off-limits.** It is decrypted
  and plaintext at rest on this machine; the encryption protects the remote only.
- **`_Alfred` cannot take a plain worktree.** `git worktree add` dies with
  `smudge filter git-crypt failed` because a worktree has no key. Use a sparse checkout that never
  materialises the vault: `git worktree add --no-checkout`, then `git sparse-checkout init --no-cone`,
  `git sparse-checkout set '/*' '!/Vault/'`, then `git checkout`.
- **Seeding a worktree's `.studio/` with `cp -R` silently no-ops** when the repo tracks any file
  under `.studio/` — `update` then says "Studio not installed". Copy `source`, `VERSION` and
  `MANIFEST.json`, not the directory.
- **The finish-check's own failure mode is silence.** A Stop hook that cannot start is one the
  harness lets through, so a dangling symlink or a bad path disables it with no error anywhere.

## Files & artifacts

- Spec: `specs/shipped-finish-check.md` (`approved`), evidence `specs/shipped-finish-check-eval-results.md`.
- Code: `studio/finish_check.py`, `_install_stop_hook` + `_FINISH_CHECK_MARKER` + `FINISH_CHECK_SENTINEL`
  in `studio/install.py`, `--no-finish-check` in `studio/run_phase.py`.
- Tests: `studio/tests/test_finish_check.py`, `studio/tests/test_hook_install.py`.
- Debate: `studio/output/tech/run_tech_20260928_163630/` — two advocate passes, two contrarian
  rejections, seven decisions.
- Concerns: `reviewer-concerns/finish_check_ships_with_studio.md`, `.../finish_check_install_entry.md`.
- Open issues: #207, #198, #181, #180. None blocks a consumer.

### Install drift, measured 2026-09-29 (local checkouts)

| behind `main` | installs |
|---|---|
| 29 | Orkid Garden, OrcPunk-dotcom, CREA, cemetery-security, miresu, Multica, _Cerebro *(stale checkout; its update PR merged)* |
| 193 | Tycho *(stale checkout; its update PR merged)* |
| 225 | _Alfred |
| 235 | OrcPunk-biz |
| 341 | Arkadium/solitaire-game |

None of them carries `finish_check.py` yet — unit 2 merged after the last sweep.

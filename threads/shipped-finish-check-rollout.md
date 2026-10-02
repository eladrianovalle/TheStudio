---
type: thread
status: active
slug: shipped-finish-check-rollout
created: 2026-09-29
updated: 2026-10-02
---

# Ship the finish-check Stop hook to every install

## Goal
Every Studio install gets the finish-check hook, so a session on any machine — not just the one it
was hand-wired on — is refused its first stop while work nothing is blocking sits undone. Done when
the eleven installs carry it and `specs/shipped-finish-check.md` reaches `status: shipped`, which
costs the evidence file.

## Where this stands

**Done and verified.**
- Spec merged (#210), approved with its evidence file opened empty (#211).
- Unit 1 merged (#213): `studio/finish_check.py`, hardened. `.claude/hooks/finish-check.py` retired.
- Unit 2 merged (#215): `_install_stop_hook`, `--no-finish-check`, the `.studio/finish-check.off`
  sentinel, docs in four files, and the pointer in `obligation-queue.md`'s Non-Goal.
- The comment rule that two downstream reviewers had to teach us is in the shipped coding
  principles (#214), so it reaches every install's `CLAUDE.md`.
- Check that `main` is clean and green rather than taking it from here (`git log -1`,
  `cd studio && python -m pytest tests/ -q`). The obligation queue reports nothing owed beyond its
  rough "built but never planned" figure.
- **The rollout ran on 2026-09-29. All eleven installs now carry the registration** —
  `grep -c finish_check.py <repo>/.claude/settings.local.json` returns 1 in every one.
- **The hand-wired global `Stop` registration is gone** from `~/.claude/settings.json` (a backup of
  the old file is only in that session's scratchpad, so treat it as gone). The worktree-prune Stop
  hook beside it was kept. The now-unreferenced symlink `~/.claude/hooks/finish-check.py` is still
  on disk, pointing at `studio/finish_check.py`; nothing runs it.
- **The Studio source repo registers its own**, in `.claude/settings.local.json`, pointing at
  `studio/finish_check.py` — it has no `.studio/`, so the installer's path would not resolve here.
  That file is gitignored, so this is machine-local and not in any commit.

**In flight.** Studio's #216 and #217 have both merged, and the rebuild they were blocking ran on
2026-09-30. Every consuming repo but OrcPunk-dotcom has a pull request carrying the refreshed
snapshot: the rollout itself where it was rebuilt before it merged, or a correction (#145, #159)
where the rollout had already merged with the earlier text. OrcPunk-dotcom's rollout merged before
it was rebuilt, and its correction has not been opened. Which of the rest are still open is the one
thing not worth writing down — it changed three times while this note was in review. Run
`gh pr list --repo <slug>` for that; what each pull request is for does not change:

| repo | PR | what it is |
|---|---|---|
| Tycho | #33 | the rollout, re-vendored before it merged |
| Orkid Garden | #144, then **#145** | #144 merged carrying the superseded text; #145 is the correction |
| Multica (orc-review) | #153, then **#159** | same story; #159 is the correction |
| Cerebro | #228 | the rollout, refreshed in place |
| OrcPunk-biz | #22 | the rollout, refreshed in place |
| cemetery-security | #723 | the rollout, refreshed in place |
| OrcPunk-dotcom | #83, then **one still owed** | #83 merged carrying the superseded text, never rebuilt; no correction is open yet |
| Alfred | #396 | the rollout, refreshed, `Owns:` fork re-applied by hand a second time |

**The installs that get the hardened hook only through a merge** are the ones whose `.studio/` is
tracked, where the script reaches disk only once the pull request merges and the live checkout
pulls it: Tycho, which got it when #33 merged and was pulled, and Alfred, OrcPunk-biz and Orkid
Garden. Until theirs merges and is pulled, Alfred and OrcPunk-biz have no script on disk, so their
hook is registered and is a clean no-op, by design — the command starts with `[ ! -f … ] ||`. Orkid
Garden is the odd one: until #145 merges and is pulled it has a script on disk, but the superseded
one, because #144 merged early.

**What the rebuild was for.** Reviewers on two consuming repos raised seven Considers about the
vendored text, and every answer went upstream rather than into a local patch, which would be a fork
the next update clobbers. The principle in `CLAUDE.md` is one line now instead of six; the
finish-check hook's marker directory is per-user and checked for ownership and mode before it is
trusted; the marker write refuses to follow a symlink; and the POSIX-only names it needs cannot
raise at import.

**Next action.** Open the correction OrcPunk-dotcom is owed: re-splice the marker block in its
`CLAUDE.md` from Studio `main`, the way #159 did for Multica. `gh pr list` on that repo comes back
empty, and that does not mean it is done. Then merge whatever is still open above and pull each
merge into its live checkout, and the evidence file is the only thing left.

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
- **The rollout left every live checkout exactly as found** — same branch, same dirty files. Four
  repos sitting on their default branch took an in-place update plus a branch; the rest were built in
  throwaway worktrees off `origin/<default>`.

## Blocked on

- **Adriano, to merge the consuming-repo pull requests still open above, then pull each merge into
  its live checkout.** Merged on GitHub is not finished: Alfred and OrcPunk-biz keep an inert hook
  until theirs is merged and pulled, and Orkid Garden runs a superseded copy until #145 is.
- **OrcPunk-dotcom's correction, which nobody has opened.** Its `CLAUDE.md` keeps the superseded
  six-line principle until a pull request re-splices it and that is merged and pulled.
- **The evidence file**, `specs/shipped-finish-check-eval-results.md`, still four `FILL_ME`s.
  `verification_due: 2026-10-28`; once that passes with it blank the suite goes red. The spec stays
  `approved` until it is filled. Pass criterion: across 30 consecutive blocked stops outside this
  repo, at least 8 produce a concrete change in the following turn.

## Landmines

- **The registration can never travel in a pull request.** `_merge_hook_entry` always writes
  `.claude/settings.local.json`, which is gitignored everywhere, because the command names an
  absolute interpreter path. So *every* install needs a run against its live checkout, no matter what
  its PR carries. A sweep that only builds worktree PRs delivers the script and no hook.
- **Alfred's `Owns:` fork is live on `master`, and an earlier reading of this said otherwise.** That
  reading came from Alfred's local checkout, which is **76 commits behind** `origin/master` on a stale
  feature branch that predates the commit adding the fork. `check-install` against that checkout
  passes and means nothing. The update against `origin/master` blocks on
  `.claude/commands/spec.md` and needs `--force` plus re-applying the fork by hand — done in #396,
  adapted to the new unit shape (a level-3 heading per unit, not a nested list). Issue #207 is the
  real fix.
- **Always pull before believing a drift report.** Same class as the Alfred mistake: Cerebro and
  Tycho were once written up as "behind" when their own merged update PRs simply had not been pulled.
- **A branch switch takes the snapshot back with it.** In a repo whose `.studio/` is tracked,
  committing the update on a branch and returning to the default branch removes
  `.studio/source/finish_check.py` from disk again. That is how an install above comes to have no
  script on disk (Alfred's was removed deliberately). Do not hand-copy it back — the merge would
  then refuse to overwrite an untracked file.
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
  `git sparse-checkout set '/*' '!/Vault/'`, then `git checkout`. Used for #396 on 2026-09-29; it
  works.
- **Seeding a worktree's `.studio/` with `cp -R` silently no-ops** when the repo tracks any file
  under `.studio/` — `update` then says "Studio not installed". Copy `source`, `VERSION` and
  `MANIFEST.json`, not the directory. The 2026-09-29 sweep needed no seeding: every repo whose
  `.studio/` is gitignored was already on its default branch or took the update in place.
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
- Every consuming-repo branch from the rollout is named `chore/studio-finish-check-hook`.

### Installs with no pull request
`miresu`, `Arkadium/solitaire-game` and `CREA` track neither `CLAUDE.md` nor `.studio/` (CREA is not
a git repository at all), so the in-place update *is* the delivery. All three are live now.

---
type: thread
status: active
slug: studio-improvements-from-evidence
created: 2026-09-15
updated: 2026-09-20
---

# Improving Studio from what its own artifacts say, not from intuition

## Goal
Studio gets measurably better at the things people actually use it for.

**The first stretch's condition is met** — `/forge` now works in a repo without anyone hand-writing
a config file. What that took, and its state, is the first entry under Where this stands; this
section does not keep a second copy. The stretch still open is the completion ledger — a session
knowing what was planned and never built — and carrying both to the installs.

## Where this stands

**Done and verified (2026-09-15 to 2026-09-20)**

*This note records no moving number — no main SHA, no test count. Both went stale inside a day and
each was caught by a reviewer. Read them from the repo instead: `git log -1` for the commit,
`cd studio && python -m pytest tests/ -q` for the suite, `ruff check .` from the root for lint.*

- **#169 — cleanup no longer eats finished work.** `cleanup_runs` deleted on age and size alone and
  never checked status; a finalized APPROVED debate died at 30 days like an abandoned prepare. 31+
  consumer runs were already lost. Finalized runs are now never deleted by either rule; unfinished
  prepares still age out; unreadable metadata counts as unfinished.
- **#169 — the finding verifier is wired in and has now run for real.** It had never run once: all 44
  findings everywhere carried `verified_confidence: null`. `finalize` now prints the
  `/finding-verifier <run_dir>` invocation when medium-confidence findings lack a verdict. It fired
  unprompted on the first debate after shipping and did real work: 5 verified, 4 promoted to high,
  1 demoted to low.
- **#171 — `findings.json` carries `schema_version`**, and the loader reads both that and the bare
  list every earlier run wrote. Verified against real archived runs. The write-back through the new
  shape is proven: the verifier round-tripped it on 2026-09-15.
- **#168 — the `/forge` refusal tells a repo with no tests that having none is the answer**, instead
  of advising a test command it can never have.

- **`specs/first-class-forge-gates.md` is built end to end — spec and all three units merged.**
  #172 put the spec on main; #175, #178 and #176 built the wizard, the mutation-check reason and the
  loader in that order. The repo's own config file is now the only thing that decides how `/forge`
  gates it: a `[gate]` key the file leaves out is empty rather than a guess, and when the gate cannot
  run the refusal names the file it read and says whether the key was blank or the file absent.
  Unit 3 shipped one fix past its criteria — the schema can require `performed` but cannot demand a
  `reason` when it is false, so `{"performed": false}` still validated; that rule lives in the
  orchestration now. The debate is `studio/output/tech/run_tech_20260915_015039`, finalized APPROVED.
  **The spec is flipped to `shipped`** — #183 merged 2026-09-19.

- **The gate-config sweep is done, and it tested the wizard rather than bypassing it.** Merging the
  loader unit would have broken `/forge` in **four** installs — `Arkadium/solitaire-game`, `_Cerebro`,
  `OrcPunk-dotcom` and `miresu`, each of which worked only because detection guessed a command for it.
  **Five** repos were configured by running `/studio-setup`, because `CREA` was done in the same pass;
  it was never a regression, since detection already found nothing there and `/forge` refused before
  and after. The five exercised both of unit 1's paths: pre-filled and stamped in the four Node and
  Python repos, and the blank stamped template with the "no marker file Studio recognises" line in
  `CREA`. cemetery-security and OrcPunk-biz still have no config and, like `CREA`, already refused, so
  they are not regressions either. Running the wizard instead of hand-writing the files is what
  surfaced issue #179.

- **The five templates that sweep wrote are corrected** (2026-09-19). They carried a comment saying a
  missing `[gate]` key falls back to detection — true when written, false once the loader unit merged.
  The wizard's own template text was fixed by that unit, so only those five files were affected and
  they were edited in place on this machine.

- **`specs/completion-ledger.md` is on main** (#177). Two advocate passes, two contrarian passes, both
  rejections accepted rather than argued down, eighteen recorded decisions. Debate:
  `studio/output/tech/run_tech_20260916_162723`, finalized APPROVED. **Unit 1 is merged** (#184): rule
  7 holds an `approved` spec's Build Plan to one entry shape, `stats.py` carries the fence-stripping
  section reader the later units reuse, and no two specs may plan the same `unit_id`. Zero specs were
  migrated, which is what gating the rule on `approved` alone buys. **Units 2 and 3 are in review, not
  built** — see In flight.

- **The stranded-concern sweep is closed.** 146 concerns recovered from old editor records; most
  load-bearing ones were already fixed or were recorded decisions. Fixes went to the repos that owned
  them and are tracked there, not here. See [[feedback_stranded_concerns_go_stale]].


**In flight**
- **#186** carries the ledger's units 2 and 3: `stats` reports both directions, and the SessionStart
  hook already running in every install names one unfinished unit plus the exact `/forge` command.
  Nothing is stored — every run re-reads the specs and re-derives the built set from git. It found
  real work the first time it ran: `stale_configs_get_the_new_command`, planned in
  `detected-static-check-command` and never built. The only other thing open in Studio is **#182**,
  this note. For what is open right now read `gh pr list` rather than this line — every revision of
  this note that carried its own copy of that list went stale before it could merge.
- Three issues from the 2026-09-16 work are open and unassigned: **#179** (`setup --defaults` resets
  every prior choice, and `--status` recommends it), **#180** (per-scope `model` in `scopes.toml`),
  **#181** (measure whether the contrarian's confidence ratings are calibrated). #180 is deliberately
  blocked on #181.

**Next action**
The cross-repo sweep, which carries the ledger and the gate work out to the installs — the roster,
and the command that re-derives it, are in Landmines. The session brief needs no installer change —
the hook already runs `check-updates --target $CLAUDE_PROJECT_DIR`, so `/studio-update` alone is
enough.

## Decisions made
- **Detection is demoted, not improved.** It becomes the setup wizard's opening guess and leaves the
  runtime path entirely. Its success rate across the four heaviest `/forge` users is **zero** —
  nothing found in `_Alfred`, `Multica`, `Orkid Garden`; two stacks at once in `cemetery-security`,
  which is also a refusal. Growing it is open-ended and a confident wrong guess is worse than none.
- **The wizard always writes a config**, pre-filled when it recognises the stack, blank with
  instructions when it does not, and **stamps what it wrote** so it can tell its own untouched
  template from a person's file. It still never overwrites anything. This closes issue #133 whole,
  so that issue no longer needs narrowing to concern 2.
- **The config file is authoritative; a missing `[gate]` key is empty, not a default.** Inseparable
  from deleting `LoopConfig`'s gate literals — see Landmines.
- **The gate-config sweep runs the wizard, never a hand-written file.** Hand-writing a config tests
  nothing: the wizard is what unit 1 changed, and it is the only path that exercises the stamp and
  the blank-template text. Doing it that way also caught #179.
- **PRs go to main, one per feature, and an agent never merges.** Written down in Studio's coding
  principles for the first time (#185, merged 2026-09-20), after three conventions this project
  runs on turned out to exist only in Adriano's head: "rejected" is a reviewer's comment verdict
  rather than a GitHub state, a fix to an open PR is a commit on that branch, and a spec's units
  travel in one PR.
- **`is_wizard_template` means stamped AND `test_command` still blank.** Unit 1's fifth criterion says
  "a file the wizard wrote and untouched", which read literally would also cover a pre-filled Python
  file; the spec's own reasoning says the blank command beside the stamp is the only state that
  matters. The narrower reading is what unit 1 was built against.
- **A human fills a blank template, not an agent.** The wizard's Python step cannot ask, and a
  proposed value waved through by a tired reader reintroduces the guessing this removes.
- **This spec gets no `## Verification` section.** Everything in it is catchable by a failing test,
  so prose beside the test would be theatre. No `verification_due`, no evidence file.
- **Copy the two-arm eval design; do not move prompt-shaped features to skills yet.** Anthropic's
  `claude plugin eval --ablation with-without` cannot see our features: its sandbox never reads the
  consuming repo's `CLAUDE.md`, which is our only vector. Revisit at a third prompt-shaped feature.

## Blocked on
- **Adriano — `is_wizard_template` still has no reader, and the sweep did not become one.** Unit 1
  built it because criterion 5 asks for it, but nothing in shipped code calls it: the wizard decides
  with `if config_path.exists()` and keeps any existing file, stamped or not. The 2026-09-16 sweep
  was the candidate reader and it turned out not to be — it ran `/studio-setup`, which never calls
  the function. So the remaining options are `update` refreshing its own untouched template while
  still refusing to touch a hand-written file, or dropping the function and letting the stamp be
  provenance a person reads. **`update` is now the likelier answer**, since it is the only thing that
  revisits a repo after setup has run.
- **Adriano — four consumer PRs still open**, contrary to what an earlier note in this repo implied:
  `OrcPunk-biz` #19, `cerebro` #226, `OrcPunk-dotcom` #82, `cemetery-security` #721. The first two
  are what `specs/detected-static-check-command.md` needs to reach `shipped`; its three acceptance
  criteria are already met. (`_Alfred` #270 and `orc-review` #102 did merge.)

## Landmines
- **Deleting detection from the loader without deleting `LoopConfig`'s gate literals recreates the
  bug it fixes.** Those literals (`pytest -q`, `ruff check {paths}`, `require_mutation_check=True`,
  `mutmut run`) are harmless today only because the loader always passes gate keys in — which is true
  *because* it consults `resolve_profile`. `Multica`'s config sets only `test_command`, so it would
  fall through to them. Verified: the only production constructions of it are inside
  `load_loop_config` itself.
- **`setup --defaults` resets every prior choice** (#179), and `--status` recommends it right after
  saying one step is pending. `_Cerebro` lost its role pack and five customizations this way; the
  config files on disk survive, so restoring `SETUP.json` and adding just the new step puts it right.
- **A template the wizard already wrote is never corrected.** setup never overwrites an existing
  file, by design — so when a change makes the template's own comment text wrong, every copy already
  on disk stays wrong until someone edits it. This fired once: the five templates written 2026-09-16
  said a missing `[gate]` key falls back to detection, which the loader unit made false. They were
  corrected in place 2026-09-19. **The lesson is the ordering:** a change to template text leaves a
  tail of files carrying the old text, and the tail is only findable by knowing when the sweep ran.
- **A refusal that names a fix must check the fix is not already done** (resolved 2026-09-19). The
  no-command refusal used to end "Or run /studio-setup, which writes that file for you" on every
  branch — which, once the wizard always wrote a file, told someone who had just run it to run it
  again. `_no_test_command_message` now branches on `config_path.exists()` (`studio/impl_loop.py:313`):
  the sentence survives only in the no-file arm, where it is correct, and the file-exists arm points
  at the blank `test_command` line.
- **Unit order was load-bearing, and the order held** (resolved 2026-09-16). The loader unit changes
  `_no_test_command_message`'s signature while `setup.py` still calls the old one, and deletes refusal
  text `test_setup.py` asserts on — so the wizard unit had to go first, and did. Kept because the
  same trap applies to any future unit pair that moves a signature one side of a caller at a time.
- **Re-including a file under an ignored directory takes TWO `.gitignore` lines.** Git cannot
  re-include a file whose parent directory is excluded, so `studio/.studio/` must become
  `studio/.studio/*` before `!studio/.studio/implementation_loop.toml` does anything. Tested both
  ways. **Check it with `git ls-files`, never `git check-ignore`** — the latter's `-v` output on a
  negated pattern reads as a match either way and will tell you it is ignored when it is not.
- **The refusal must branch on whether the file exists**, not on which resolution path supplied it.
  Branching on "is this the project override" mis-reports an explicitly passed file with a blank key
  as a missing file, which hits every `load_loop_config(path=...)` caller.
- **`cemetery-security` is an armed trap.** 53 `/forge` units, more than any repo, **no config file**,
  and detection returns two stacks at once. `/forge` refuses there today. It went quiet 2026-08-10, a
  week before stack-aware gates shipped, so the change did not break it — it hits the wall on its
  first attempt whenever it wakes up. Nothing in this spec rescues it automatically; it needs the
  wizard run.
- **External research is a low-yield channel for Studio.** A five-agent sweep — verdict
  re-validation, 43 AI-Radar notes, the orchestration landscape, eval tooling — flipped zero verdicts
  and produced two small borrows. Pointing one agent at our own run artifacts produced everything
  that mattered. Related: the artifacts were nearly all deleted, which is what #169 fixed.
- **Commission the usage analysis with a re-derived roster, never a remembered list.** Briefing an
  agent with 8 repos missed `Arkadium/solitaire-game` (18 forge units, an active user) and `CREA`.
  The roster is **11 installs** as of 2026-09-20 — a later briefing that said 10 missed `Tycho`, which
  is the same mistake one level down. Re-derive it every time:
  `find "$HOME" -maxdepth 6 -name VERSION -path "*/.studio/*"`.
- **`spec/editor-breadth-valve` is an orphaned branch on origin** — 293 lines of spec from
  2026-07-28 whose PR #78 was closed unmerged. Not lost, but it belongs to a rejected item; do not
  mistake it for live work.

## Files & artifacts
- Repo: this checkout. The note deliberately records no main SHA;
  read it from git.
- Specs: `specs/first-class-forge-gates.md` and `specs/completion-ledger.md`, both on main. Their
  status lives in their own frontmatter; this note does not keep a second copy of it.
- `git worktree remove` destroys a run's gitignored records — the `.studio/output/impl_loop/` handoffs
  and anything not committed. Copy them out before removing a `/forge` worktree, and commit the
  `reviewer-concerns/` file, which is written outside the ignored directory precisely so it survives
  but which nothing commits for you.
- Debate: `studio/output/tech/run_tech_20260915_015039` — instructions, decisions, both advocate and
  contrarian rounds, verified `findings.json`, summary. Survives cleanup now that #169 shipped.
- Ticket: [#133](https://github.com/eladrianovalle/TheStudio/issues/133), closed by the shipped
  gate work.
- Other live threads in this repo: `game-design-boards.md` (eval arms built and verified in Orkid
  Garden, clear to run from 2026-09-15), `studio-rollout-and-open-prs.md`,
  `reviewer-concerns-rescued.md`.
- Evidence behind all of this: the memory note `project_studio_usage_evidence.md`.

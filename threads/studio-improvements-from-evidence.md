---
type: thread
status: active
slug: studio-improvements-from-evidence
created: 2026-09-15
updated: 2026-09-19
---

# Improving Studio from what its own artifacts say, not from intuition

## Goal
Studio gets measurably better at the things people actually use it for. Done for this stretch when
`specs/first-class-forge-gates.md` is built and `shipped` — `/forge` then works in a repo without
anyone hand-writing a config file.

## Where this stands

**Done and verified (2026-09-15 to 2026-09-19)**

*One anchor, stated once: main is the head of this repo's default branch — run `git log -1` for the
SHA rather than trusting a copy here, which is how three earlier revisions of this note went stale.
As of 2026-09-19 it carries 1053 tests, ruff clean.*

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
  **The spec has not been flipped to `shipped` yet** — see Next action.

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
  `studio/output/tech/run_tech_20260916_162723`, finalized APPROVED. Nothing is built from it yet.

- **The stranded-concern sweep is closed.** 146 concerns recovered from old editor records; most
  load-bearing ones were already fixed or were recorded decisions. Fixes went to the repos that owned
  them and are tracked there, not here. See [[feedback_stranded_concerns_go_stale]].

- **The completion ledger's unit 1 is merged** (#184, 2026-09-19). Rule 7 holds an `approved` spec's
  Build Plan to one entry shape, `stats.py` carries the fence-stripping section reader the later
  units reuse, and no two specs may plan the same `unit_id`. Zero specs were migrated, which is what
  gating the rule on `approved` alone buys.

**In flight**
- **The ledger build is running to completion**, unit by unit. Unit 2 `stats_reconciles_units`
  reconciles both directions and prints the `stats` block; unit 3 `session_brief_names_the_next_unit`
  turns `check-updates` into a two-source brief. This note is deliberately not updated per unit —
  three of its revisions were rejected for carrying stale copies of fast-moving facts, so it gets one
  update when the ledger is done.
- **#182** (this note) and **#183** (`first-class-forge-gates` to `shipped`, closes #133) are open.
- Three issues from the 2026-09-16 work are open and unassigned: **#179** (`setup --defaults` resets
  every prior choice, and `--status` recommends it), **#180** (per-scope `model` in `scopes.toml`),
  **#181** (measure whether the contrarian's confidence ratings are calibrated). #180 is deliberately
  blocked on #181.

**Next action**
Finish the ledger — units 2 and 3 — then the cross-repo sweep that carries all of this to the
installs.

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
  fall through to them. Verified: the only production constructions are inside `load_loop_config`
  itself (`impl_loop.py:551`, `:576`).
- **`setup --defaults` resets every prior choice** (#179), and `--status` recommends it right after
  saying one step is pending. `_Cerebro` lost its role pack and five customizations this way; the
  config files on disk survive, so restoring `SETUP.json` and adding just the new step puts it right.
- **A template the wizard already wrote is never corrected.** setup never overwrites an existing
  file, by design — so when a change makes the template's own comment text wrong, every copy already
  on disk stays wrong until someone edits it. This fired once: the five templates written 2026-09-16
  said a missing `[gate]` key falls back to detection, which the loader unit made false. They were
  corrected in place 2026-09-19. **The lesson is the ordering:** a change to template text leaves a
  tail of files carrying the old text, and the tail is only findable by knowing when the sweep ran.
- **Unit 2 must also kill the refusal's last line.** It still ends "Or run /studio-setup, which writes
  that file for you." After unit 1 that sentence tells someone who just ran the wizard to run it
  again, at a file that already exists with the `[gate]` block in it. Unit 2 already owns rewording
  the refusal around whether the file exists; drop the sentence from the file-exists branch and point
  at the blank `test_command` line instead.
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
  The roster is 10 installs: `find /Users/orcpunk -maxdepth 6 -name VERSION -path "*/.studio/*"`.
- **`spec/editor-breadth-valve` is an orphaned branch on origin** — 293 lines of spec from
  2026-07-28 whose PR #78 was closed unmerged. Not lost, but it belongs to a rejected item; do not
  mistake it for live work.

## Files & artifacts
- Repo: `/Users/orcpunk/Repos/_TheGameStudio`. The note deliberately records no main SHA;
  read it from git.
- Spec: `specs/first-class-forge-gates.md`, on main and `approved`.
- Unit 1's tree: `/Users/orcpunk/Repos/_TheGameStudio-wt-forge-gates`, branch
  `impl/wizard_writes_stamped_template`. Remove the worktree only after its PR is open — a
  `git worktree remove` destroys the run's gitignored records.
- Debate: `studio/output/tech/run_tech_20260915_015039` — instructions, decisions, both advocate and
  contrarian rounds, verified `findings.json`, summary. Survives cleanup now that #169 shipped.
- Ticket: [#133](https://github.com/eladrianovalle/TheStudio/issues/133), which #172 supersedes.
- Other live threads in this repo: `game-design-boards.md` (eval arms built and verified in Orkid
  Garden, clear to run from 2026-09-15), `studio-rollout-and-open-prs.md`,
  `reviewer-concerns-rescued.md`.
- Evidence behind all of this: the memory note `project_studio_usage_evidence.md`.

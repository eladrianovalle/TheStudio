---
type: thread
status: active
slug: studio-improvements-from-evidence
created: 2026-09-15
updated: 2026-09-15
---

# Improving Studio from what its own artifacts say, not from intuition

## Goal
Studio gets measurably better at the things people actually use it for. Done for this stretch when
`specs/first-class-forge-gates.md` is built and `shipped` — `/forge` then works in a repo without
anyone hand-writing a config file.

## Where this stands

**Done and verified (2026-09-15)**
- Main at `fcb14ed`, **1033 tests**, ruff clean (1043 on unit 1's branch).
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

- **#172 merged 2026-09-15**, so `specs/first-class-forge-gates.md` is on main and its frontmatter is
  `status: approved` (commit `8f68a33`, on the unit-1 branch). The debate behind it is
  `studio/output/tech/run_tech_20260915_015039`, finalized APPROVED, with `decisions.md`,
  `findings.json` (verified) and `summary.md` all present.

- **#174 merged 2026-09-15**, so this note is on main.

- **Unit 1, `wizard_writes_stamped_template`, is built and open at PR #175.** Delivered unflagged:
  all five acceptance criteria graded `pass` with evidence, editor edited without reverting, 1043
  tests green (10 new), ruff clean, mutation check caught all four mutations. Worktree
  `/Users/orcpunk/Repos/_TheGameStudio-wt-forge-gates`, branch `impl/wizard_writes_stamped_template`.

**In flight**
- **PR #175 awaiting review.** Its `reviewer-concerns/wizard_writes_stamped_template.md` carries the
  two things the editor found and could not fix in the pass — see Blocked on, and Landmines.

**Next action**
After #175 merges: unit 2, `gate_keys_resolve_to_none`. **Unit order is a correctness constraint, not
a preference** — see Landmines.

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
- **Adriano — `is_wizard_template` has no reader, and only a spec change can give it one.** Unit 1
  built it because criterion 5 asks for it, but nothing in shipped code calls it: the wizard decides
  with `if config_path.exists()` and keeps any existing file, stamped or not. So the distinction the
  spec says the stamp exists for is never actually made. Either give it a reader — the cross-repo
  sweep, or `update` refreshing its own untouched template while still refusing to touch a
  hand-written file — or drop the function and let the stamp be provenance a person reads. **The
  sweep is the likelier answer**: it is the one place that wants to rewrite ten repos' templates
  without touching anyone's edits.
- **Adriano — merge PR #175** (unit 1).
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
- **Unit 2 must also kill the refusal's last line.** It still ends "Or run /studio-setup, which writes
  that file for you." After unit 1 that sentence tells someone who just ran the wizard to run it
  again, at a file that already exists with the `[gate]` block in it. Unit 2 already owns rewording
  the refusal around whether the file exists; drop the sentence from the file-exists branch and point
  at the blank `test_command` line instead.
- **Unit order is load-bearing.** The loader unit changes `_no_test_command_message`'s signature
  while `setup.py` still calls the old one, and deletes refusal text `test_setup.py` asserts on.
  Build the wizard unit first.
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
- Repo: `/Users/orcpunk/Repos/_TheGameStudio`, main `13e689a`.
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

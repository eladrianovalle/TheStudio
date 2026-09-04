# Find Before You Grep — Verification Results

**Spec:** [`find-before-you-grep.md`](./find-before-you-grep.md). The pass criterion below was copied
from that spec before anything was measured. Don't edit it to match what happened — if it turned out to
be the wrong criterion, say so under "What this doesn't prove."

Every placeholder below marks data that does not exist yet. Replacing one is the act of reporting.
Dropping a whole section, or clearing a placeholder and writing nothing under its heading, fails the
suite once this spec says `status: shipped` — every heading here needs an answer you wrote yourself.

## Pass criterion (written before the build)
> This feature works if and only if, in a `/forge` or `/spec` run inside a repo that has a code index,
> the agent (a) uses that index to locate code before grepping or opening files blind, **and** (b) every
> quoted piece of evidence in its output is traceable to the file at the returned `file:line` rather
> than to the index's own summary or excerpt.

## What happened

Measured 2026-09-04. Two isolated clones of this repo at `c2cd45d`, each with a freshly built graft
index (1,647 nodes) and a `CLAUDE.md` section naming the tool — that wiring is the consuming repo's job
per the spec, so it is present in both arms. The arms differ **only** in Studio's three prompt clauses,
stripped from the baseline (`implementation-loop.js` writer and editor, `spec.md`). Both scripts were
checked to parse; the arms were diffed to confirm no other file differs.

Instrument: a `/spec` discovery pass, which the criterion names as an equal alternative to `/forge`.
Each arm was given the same architecture question requiring a multi-file code trace ("how does `update`
decide an installed file must not be overwritten"), and asked to report its tool calls in order.

| Condition | What was run | Times | Criterion met | Notes |
|---|---|---|---|---|
| Baseline, in-session subagent | clauses stripped, graft skill in scope | 1 | **yes** | Loaded the graft skill unprompted, then `graft ask` → `graft grep` → targeted `sed`. No blind sweep. |
| Treatment, in-session subagent | clauses intact, graft skill in scope | 1 | yes | `graft_find_code` → `graft_find_all` → targeted `sed`. One blind `grep`, its only failed call. |
| Baseline, clean room | clauses stripped, no skill/hooks/MCP | 1 | **no** | 13 calls, every one Bash. `ls`, then a broad `grep -rn` sweep, then `sed`. Never touched the index. |
| Treatment, clean room | clauses *not loaded* — see below | 1 | **no** | 12 calls, every one Bash. `ls`, `grep -n "update"`, `grep -n "^def "`, then `sed`. Never touched the index. |

| Baseline, clean room, `/spec` | clauses stripped, no skill/hooks/MCP, clause loaded via `/spec` | 1 | **no** | 7 calls, every one Bash. `ls`, a broad `grep -n` sweep of `install.py`, then `sed` at guessed line ranges. Never touched the index. |

Tool-call orders were read off the session transcripts on disk, not taken from any session's own
account of itself.

| Treatment, clean room, `/spec` | clauses intact, no skill/hooks/MCP, clause loaded via `/spec` | 1 | **yes** | 16 calls. Call 1 `ls` to orient, **call 2 `graft ask "…" --source`** — before any grep and before opening any file — then `sed`/`grep` at the spans it returned. Quotes taken from the files, not from the index output. |

**The last two rows are the measurement.** Same clean room, same question, same index, same
`CLAUDE.md` naming the tool. The only difference between the two directories is the three clauses.
Baseline swept with grep and never touched the index; treatment reached for it on its second call and
opened files at the addresses it returned. Both criterion halves are met in treatment and (a) fails
in baseline, which is what the criterion asks for.

The four earlier rows are void and kept only so the record shows what was tried. The first pair had
no working baseline: subagents inherit the session's skills rather than the working directory's, so
this repo's graft skill — whose description is Studio's clause in different words — was in scope for
both arms. The second pair had no working treatment: the clause lives in files that load only when
`/spec` or `/forge` is invoked, and those runs used a bare pasted prompt.

One observation about the instrument, not the feature: the `/spec` session declined to run a debate,
correctly noting the question asked how existing code works rather than asking for a feature to be
designed. It traced the code instead. That does not affect the measurement — the clause loads when
the command is invoked, regardless of what the session then decides to do.

The baseline row should read "no". If the criterion was already met with the feature off, stop and
say so: a feature that fixes a problem you could never trigger has not been shown to do anything.

**Neither pair is a valid test, and each fails for its own reason.**

*The in-session pair had no working baseline.* Subagents inherit the session's skills rather than the
working directory's, so this repo's graft skill was in scope for both arms. Its description reads:
*"For ANY task here … get your context from graft before grepping or reading source files."* That is
Studio's clause in different words, arriving through a channel the rig could not switch off.

*The clean-room pair had no working treatment.* The clause lives in `.claude/commands/spec.md` and in
the workflow's writer and editor prompts — files that load only when `/spec` or `/forge` is actually
invoked. The runs used a bare pasted prompt, so the treatment arm never had the feature switched on.
Verified after the fact: neither arm's `CLAUDE.md` contains the clause, which is why the two behaved
identically. This was an instrument design error, not a property of the feature.

**A supporting finding from the void runs:** the repo naming its index tool is not sufficient on its
own. Both bare-prompt arms carried a `CLAUDE.md` section reading "This repo is indexed by graft" with
usage examples, and both ignored it across 25 tool calls. That is the gap the clause fills, and it
explains why the valid baseline behaved as it did despite having the tool named in front of it.

## What this doesn't prove

Required — this section is the point of the file.

**The criterion passed as written. It was not rewritten after the fact** — it is the same *iff*
copied from the spec before any run, and no number moved the wrong way. Cost was comparable: 7 calls
in baseline against 16 in treatment, but the treatment session spent its extra calls going on to
diagnose and fix an unrelated bug after the trace was done, which is not chargeable to the clause.

**The sample is one run per arm. That is the main limit and it is a real one.** A single pair cannot
speak to consistency, and agent tool choice varies between runs. What makes this worth reporting at
n=1 rather than nothing is the size and shape of the difference — not a marginal shift in call order
but index-on-the-second-call versus never — together with a mechanism that is not mysterious: an
instruction present in context versus absent from it.

**What a reader could wrongly conclude:**
- *That the clause works everywhere.* It was tested in one repo, on one question, with one index
  tool, under `/spec`. `/forge` carries the same clause in its writer and editor prompts and was
  never exercised.
- *That the clause is what makes agents use an index.* It is one of several things that do. A skill
  carrying an imperative instruction had the same effect in the void runs, and would mask the clause
  entirely in any repo that has one.
- *That the question was representative.* It was a multi-file trace through unfamiliar code — the
  shape where an index pays off most. A single-file question might show no difference at all.

**Conditions not tested:** a repo with an index that its `CLAUDE.md` does *not* name; a repo with no
index (the intended no-op case); `/forge` as the instrument; any index tool other than graft; any
repo other than this one.

**An alternative explanation that cannot be ruled out at n=1:** run-to-run variance. The two sessions
were separate processes with no shared state, and nothing forces a given session to open with `ls`
and then a grep sweep. A second pair would narrow this; it has not been run.

**A note on the instrument for anyone repeating this.** Both sessions declined to run `/spec` as a
debate, correctly observing that the question asked how existing code works rather than asking for a
feature to be designed, and traced the code instead. That behaviour was identical across arms, so it
is not a confound — and the clause loads when the command is invoked regardless of what the session
then decides to do. The treatment clone is also no longer pristine: that session went on to edit
`run_phase.py` after the trace. Re-clone before repeating.

## Verdict

**Criterion met**, on a single controlled pair, with the sample size named above as the principal
limit.

In two directories differing only in the three prompt clauses, the arm carrying them called the code
index on its second tool call — before any grep, before opening any file — and then read the files at
the addresses it returned. The arm without them swept with grep and never touched the index, despite
its `CLAUDE.md` naming the tool with usage examples.

It took four void runs to get one valid comparison, and both failures were instrument errors rather
than properties of the feature: the first pair had no baseline because a skill supplied the clause's
instruction to both arms, and the second had no treatment because the clause lives in files that only
load under `/spec` or `/forge`. The lesson generalises to any prompt-shaped verification here: **a
baseline is only a baseline if the behaviour under test cannot reach the agent by another route, and
a treatment is only a treatment if the file carrying it is actually loaded.** Check both before
trusting a comparison.

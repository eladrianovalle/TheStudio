# Coding Principles

Behavioral guidelines to reduce common LLM coding mistakes. These apply to ALL work in this repository, not just Studio runs.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume silently. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly, then keep going. Naming an assumption is not a reason to stop.
- If two readings would produce genuinely different work, ask. If one is clearly likelier, take it and say which you took.
- If a simpler approach exists, say so. Push back when warranted.
- Stop and ask only when proceeding would be unsafe, or would waste the work if the guess turns out wrong. Otherwise: pick, say what you picked, and finish the task.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you wrote 200 lines of machinery for a 50-line problem, cut it down, but remove *concepts*, not characters. Aim for fewer moving parts, never the same logic squeezed into denser code (that's what "Write Code for Humans" guards).

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify. Overcomplicated means too many moving parts, not too many characters.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it, don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Git & PR Etiquette

**Draft means the work is still moving — not "I haven't said it's done yet."**

Open a PR as a **draft** when you intend to keep pushing to it. That guards two real failure modes: a half-finished branch getting merged by mistake, and a reviewer spending attention on a target that's still changing. When the unit is complete and its tests pass, open it **ready for review** — or flip it the moment it gets there. A finished PR sitting in draft buys nothing and costs the reviewer a round trip.

Draft is a signal about the state of the work, not a ceremony every PR passes through. Re-check the call on every push: if you thought a branch was finished and then pushed to it again, it goes back to draft.

## 6. Write for Humans

**Your docs, your code, and your updates are all read by a person. Write for that person.**

**Docs, comments, docstrings, commit messages, PR descriptions.**
- Use plain language. If a term of art is unavoidable, define it the first time or pick a simpler word.
- Cut the tells of machine-written prose: inflated phrasing, filler, hedging, and padding add length without adding meaning.
- Say what a thing does and why it matters, not just its name. "Refuses to overwrite your local edits" beats "enforces the clobber-guard precondition."
- Match the voice already in the file instead of importing your own.
- Match the length of a file to what it actually has to say — no filler sections, no restating one point three ways. CLAUDE.md and architecture docs drift toward bloat because appending is easier than editing, so prefer editing a line over appending a section.
- The test: could a teammate who is new to the code read it once and understand it, without asking you to translate?

**Code.** Its first reader is a person, not the compiler, so write code for humans. Simple and readable are not the same thing: simple code has few moving parts, readable code spells those parts out. Aim for both, and never trade readability away to save lines.
- Name things in full, for what they are. `remaining_budget` over `rb`, `resolve_source_dir` over `rsd`. A good name is a comment you don't have to write.
- Reach for the plain, conventional form a reader expects: explicit and a little verbose over compact and clever, one obvious thing per line rather than a dense expression to decode. Cleverness is a cost paid again by everyone who reads the code later.
- The test: could a teammate seeing this file for the first time read it top to bottom and follow it, without you narrating over their shoulder?

**Updates to a person: progress, questions, decisions.** They haven't opened the files you changed or the notes you kept, so nothing you name explains itself.
- Lead with what changed for them and why it matters, not the mechanism you used to get there. Keep it short and information-dense: skip preamble, restated context, and a play-by-play of work the diff already shows.
- Don't drop internal handles — file names, section numbers, config keys, ticket or PR IDs, function names — as if they carry meaning on their own. Say in plain words what the thing is, and keep the identifier only when it's something they'll act on: a link to click, a command to run, a PR to review.
- When you flag a decision or a question, give enough context and a recommendation that they can answer without digging. Say what's at stake and which way you'd lean.
- Don't narrate self-corrections. Fix the error, note it in one line only if it changes a decision the reader has to make, then move on.
- End a long update with a `## TL;DR`: one to three sentences or bullets covering what changed, anything that needs their attention, and what's next. Skip it when the update is already short enough to read at a glance.
- Plain and a little warm beats a dense status log. A person is reading this, not a build server.
- The test: could the reader act on your update — approve the call, answer the question, trust the "it's done" — without opening a single file or asking you to translate?

## 7. Spec Before Build

**A non-trivial feature gets an approved architecture spec before you build it.**

Building without a spec means the architecture gets decided implicitly, one commit at a time, with no place to see it whole and no record of why. A spec pulls the design forward: it surfaces the unknowns while they're still cheap to change, pressure-tests the structure, and gives everyone one source of truth to build against.

- Before implementing a real feature, write (or ask for) a spec — the `/spec` command runs the discovery + advocate/contrarian pass and produces one. It explains the feature in plain language *and* build-ready technical detail, with a diagram.
- The spec is the source of truth only once a human approves it. Then the build follows it; changes to the architecture go back through the spec, not around it.
- Track the spec with its feature: commit it under `specs/` and link it to the ticket/issue it belongs to, so the design and the work stay tied together.
- If the feature is **prompt-shaped** — its behavior lives in an agent's prompt, where no test can
  tell you it broke — the spec also writes down how you would know it works: a pass criterion agreed
  before the build, and a results file beside the spec that has to be filled in before anyone calls
  the feature done.
- This is for features and meaningful changes, not every task. A one-line fix or an obvious tweak doesn't need a spec — use judgment, the same as everywhere else.

The test: if someone asked "what are we building and why is it shaped this way?", is there an approved document that answers it — or does the answer only exist in your head and the diff?

---

*These guidelines are working if:* fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

*Adapted from [Andrej Karpathy's coding principles](https://github.com/forrestchang/andrej-karpathy-skills).*

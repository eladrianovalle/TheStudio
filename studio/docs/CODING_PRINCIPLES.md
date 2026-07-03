# Coding Principles

Behavioral guidelines to reduce common LLM coding mistakes. These apply to ALL work in this repository, not just Studio runs.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them. Don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

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

**Open pull requests as drafts first.**

A new PR starts as a **draft**, not ready-for-review. Mark it ready only when the work is complete, tests pass, and you actually want a human to review and merge it. Opening as a draft prevents two failure modes: accidental early merges (a not-yet-finished PR getting merged by mistake) and reviewer churn (reviewers spending attention on a still-moving target). Flip to ready when it's genuinely ready for eyes.

## 6. Write Docs & Comments for Humans

**A person reads your docs and comments. Write for that person.**

This covers everything you write for humans rather than the compiler: doc files, code comments, docstrings, commit messages, and PR descriptions.

- Use plain language. If a term of art is unavoidable, define it the first time or pick a simpler word.
- Say what a thing does and why it matters, not just its name. "Refuses to overwrite your local edits" beats "enforces the clobber-guard precondition."
- Cut the tells of machine-written prose: inflated phrasing, filler, hedging, and padding add length without adding meaning.
- Match the voice already in the file instead of importing your own.

The test: could a teammate who is new to the code read it once and understand it, without asking you to translate?

## 7. Write Code for Humans

**The code's first reader is a person, not the compiler. Write for that person.**

The previous principle covers what you write *around* the code: docs, comments, commits. This one is about the code itself. Simple code and readable code are not the same thing: simple code has few moving parts; readable code spells those parts out. Aim for both, and never trade readability away to save lines.

- Name things in full, for what they are. `remaining_budget` over `rb`, `resolve_source_dir` over `rsd`. A good name is a comment you don't have to write.
- Prefer explicit and a little verbose over compact and clever. One obvious thing per line beats a dense expression a reader has to decode.
- Reach for the plain, conventional form a reader expects. Cleverness is a cost paid again by everyone who reads the code later.
- Don't compress just to shorten. Saving three lines isn't worth making the next person stop and work out what they do.

The test: could a teammate seeing this file for the first time read it top to bottom and follow it, without you narrating over their shoulder?

## 8. Talk to Humans

**When you report back or ask for a decision, the reader hasn't seen what you just did. Write for that reader.**

Principles 6 and 7 cover what you write into the codebase. This one is about the live conversation: progress updates, flagging a question, surfacing a decision. The person reading has not opened the files you changed, the docs you wrote, or the notes you kept, so nothing you name explains itself.

- Lead with what changed for them and why it matters, not the mechanism you used to get there.
- Don't drop internal handles — file names, section numbers, config keys, ticket or PR IDs, function names — as if they carry meaning on their own. Leave them out, or say in plain words what the thing is and why the reader should care. Keep the identifier only when it's something they'll act on: a link to click, a command to run, a PR to review.
- When you flag a decision or a question, give enough context and a recommendation that they can answer without digging. Say what's at stake and which way you'd lean.
- Plain and a little warm beats a dense status log. A person is reading this, not a build server.

The test: could the reader act on your update — approve the call, answer the question, trust the "it's done" — without opening a single file or asking you to translate?

---

*These guidelines are working if:* fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

*Adapted from [Andrej Karpathy's coding principles](https://github.com/forrestchang/andrej-karpathy-skills).*

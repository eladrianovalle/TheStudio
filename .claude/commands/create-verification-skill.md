---
description: "Use when a repo that installed Studio has no scripted way for an agent to launch, drive and capture its running product. Studies the repo, writes a verification skill and a feature map into .claude/skills/verify-<app>/, proves them once end to end, and leaves them uncommitted for review. Triggers include 'make a verify skill for this repo', 'teach agents to drive the app', and /forge editors grading criteria unverifiable because they could not run the product."
disable-model-invocation: true
---

# Create a verification skill

Every serious project needs a scripted way to drive the real app and prove behavior: launch it, exercise a feature the way a user would, and capture evidence. This command generates that as a project-local skill (`.claude/skills/verify-<app>/`) tailored to the repo. You write the generator's output for the next agent, not for a human: it will be read cold, mid-task, by an agent that has never seen the app. One such reader is a `/forge` editor grading a unit from a fresh worktree.

The steps are pstack's. Steps and paragraphs marked **[Studio]** are Studio's additions. When a step says to ask the user, use `AskUserQuestion`; in `-p` mode it is absent, so ask in plain text.

## 0. Locate [Studio]

Look for `.claude/skills/verify-*/`. If one exists, stop and write nothing. Tell the user the repo already has a verification skill at that path and that `/maintain-verification-skill` keeps it current. A second run must never overwrite a map someone has maintained.

## 1. Interview the repo, not the user

Answer these from the codebase and only ask the user what you cannot observe:

- **Surface:** what does a user actually touch? A web UI, a CLI/TUI, a desktop app, an API, a mobile app, a library? A repo can have several; pick the primary one and note the rest.
- **Run:** how does the app start locally? Prefer the repo's own documented dev command (package scripts, Makefile, README quickstart). Note ports, env vars, seed data, auth.
- **Drive:** how can an agent interact with it programmatically? Existing harnesses first — Playwright/Cypress specs, expect scripts, PTY helpers, curl-able endpoints, a debug port. Only then pick a generic recipe: browser/CDP for web and Electron, a tmux/PTY harness for CLI/TUI, plain HTTP for services.
- **Observe:** what evidence can be captured? Screenshots, terminal transcripts, response bodies, logs, exit codes, DB state.
- **Isolate:** can two instances run side by side (ports, data dirs, profiles)? If not, say so in the generated skill: refusing to double-drive a shared instance beats corrupting the user's session.

If the checkout doesn't build or start as-is, fix that first (or report it precisely) before generating; a skill written against a broken base teaches wrong steps. When an irrelevant missing asset blocks startup (a static dir the API never serves, a sample config), the generated skill may create it, clearly marked as verification scaffolding, and remove it in cleanup.

**[Studio] Seeds, read only.** Read these before looking anywhere else, and change none of them:

- `.studio/smoke.toml`, table `[smoke]`. Its `setup`, `build`, `launch`, `ready_probe` or `ready_log`, and `teardown` are candidates for Launch, readiness and Cleanup. Each `golden_path` entry is a candidate feature.
- `[gate] observe_command` in `.studio/implementation_loop.toml`. Run it with `--help`. Wherever it covers a feature, it is the preferred entry for Drive and Evidence, because the `/forge` prompts already tell both agents to run it.
- Any driver script that `CLAUDE.md` or the package scripts name.

This is pstack's "existing harnesses first", pointed at Studio's config. There are no stack special cases: a repo that cannot drive itself fails the proof in step 5, honestly.

## 2. Generate the skill

Write `.claude/skills/verify-<app>/SKILL.md` with YAML frontmatter (`name: verify-<app>` and a `description` that names the app, the surface, and when to reach for it — without frontmatter the skill never registers) and these sections, each grounded in what the interview actually found (no placeholders left):

- **Launch:** the exact command that starts the app for verification, and how to tell it's ready (a log line, a prompt). Launch must reach a usable state from an empty data dir, including any migrations and seed data. Ready means usable, not just that a process answers. A database health check can pass while its init scripts are still running. Include teardown. For a short-lived CLI or TUI there is no server to keep alive: launch means build the binary (or install deps) once, then start each drive in its own isolated PTY or tmux session.
- **Doctor:** one read-only check that answers "is this instance worth driving?" — process up, right version/build, port owned by us, auth valid. An agent runs this first whenever anything looks off.
- **Drive:** the harness recipe with real selectors/commands from this repo, not examples. Prefer stable handles (ARIA labels, data attributes, prompt strings, route paths) over coordinates and tab order.
- **Evidence:** what to capture for a proof and where it goes. State the proof standards: exercise the real user path, not internal setters or test-only endpoints; capture the action and the resulting state, not just the final screen; verify side effects (files written, rows inserted, messages sent) alongside what's visible; mocks only where a production boundary already isolates the external system. When the safe path is a dry-run or test mode, verify what it actually skips by observing (files, network, git refs) rather than trusting its name: some dry-runs still touch the network or open a browser.
- **Cleanup:** how to tear down instances the run created. Never kill by process name; kill what you started. Cleanup removes instances and scratch state, never the evidence: proof artifacts survive the teardown, in a location the skill names.
- **Helpers:** any script the skill ships is executable and its invocation is shown in the skill body. A helper the reader has to reverse-engineer is not a helper.

**[Studio] Additions to those sections:**

- **Evidence** goes outside the checkout, for example under `$TMPDIR/<app>-verify/<short sha>-<time>/`, and the skill prints every capture as an absolute path. That is the `[gate] observe_command` contract, and anything inside the checkout would be committed or vanish with a worktree.
- **Launch** must work from a fresh `git worktree`, dependency install included, because that is where a `/forge --work-dir` editor stands.
- **Doctor** rejects a software renderer when the product needs a GPU, so a headless browser that fell back to one is never driven as if it were the real thing.

## 3. Seed the feature map

Create `.claude/skills/verify-<app>/features/README.md` plus one file per user-facing feature you can identify (aim for the top 3-5 to start, from routes, commands, menus, or docs). Follow the shape below, with a README index and one file per feature. Each file answers, from the user's point of view: what the feature is, how to reach it, how to drive it with the harness, and what observable end state proves it works. The four H2s are `Sub-features`, `How to get to it (user POV)`, `Driving it with <harness>`, and `Gotchas`. If the seed data lacks a precondition that a journey needs, the journey reports a failure and the reason goes in that feature's `Gotchas`. Never weaken the journey to make it pass. The map is the repo's maintained verification source; a proof that drives one convenient entry point is incomplete when the map lists others.

**The shape.** `features/README.md` opens with one paragraph saying the directory is the maintained source for verifying the app's user-facing behavior: read the index before driving, then use the matching feature file as the recipe. Then these H2s, in order:

- `## Baseline preconditions`: the launch target, a disposable data directory per run so concurrent runs share nothing, the seed data, the tools that must be on `PATH`, the doctor check that must pass, and a rule never to drive an instance this run did not start.
- `## Driving conventions`: start every recipe from the baseline, prefer stable handles, treat every command as literal, say which harness entry runs which kind of action, restore seed data after a mutation, and never remove evidence during cleanup.
- `## Proof and skip reporting`: capture the action and the resulting state; what a UI, CLI or mutation proof must include; record the feature and entry point with every artifact; report an unreachable path with the command tried and the precondition that was missing; never report a skipped entry point as verified through a different one.
- `## Feature entry contract`: the feature-file shape below, restated for the next reader.
- `## Features`: one linked line per feature file, naming what it covers.

Each feature file starts with an H1 title and one paragraph on the behavior a user sees, then exactly four H2s, in this order:

1. `## Sub-features`: short IDs, one line per behavior.
2. `## How to get to it (user POV)`: every entry point a user has.
3. `## Driving it with <harness>`, with `<harness>` replaced by the real harness's name: it opens with `Preconditions:`, then labeled bullets that pair each user action with the exact command and the result to observe, and ends with a proof bullet that writes the evidence.
4. `## Gotchas`: traps that waste or invalidate a verification run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands and observable proof.

## 4. Wire it up [Studio]

Add one line to the project's own part of `CLAUDE.md` (`AGENTS.md` when there is no `CLAUDE.md`). Put it outside the `<!-- STUDIO:CODING_PRINCIPLES:BEGIN -->` and `<!-- STUDIO:CODING_PRINCIPLES:END -->` block, because Studio's `update` rewrites everything between those markers. When the file has a commands block, the line goes there. Write it with the real app name:

```
- Before verifying anything a user sees, hears or runs, Read `.claude/skills/verify-<app>/SKILL.md` and `.claude/skills/verify-<app>/features/README.md`, then the feature file that covers it.
```

The line names files to Read, never a skill to invoke: `/forge`'s headless roles run with slash commands disabled and never see a project skill, but a checkout's `CLAUDE.md` still reaches them. Write the line once. If a line already points at this skill, leave it as it is.

## 5. Prove the generated skill before handing it over

Run its own instructions end to end once: launch, doctor, drive ONE mapped feature (one is enough; the map exists so later runs can cover the rest), capture evidence, clean up. After cleanup, confirm the evidence still exists at the named location — a cleanup that eats the proof fails this step. Fix what fails, and run the generated cleanup after every failed iteration too, so broken attempts don't strand processes and ports. A generated skill that was never executed is a draft, not a deliverable. If you proved it in a stand-in for the real target (a container in place of a fresh VM, a local stack in place of a remote one), list every setup step the stand-in did that the target will not. Those steps stay unverified until a run on the real target covers them.

**[Studio] Prove it in a fresh worktree, never in the person's checkout.** With `<scratch>` a directory outside the checkout:

```
git worktree add --detach <scratch>/verify-proof HEAD
```

Copy `.claude/skills/verify-<app>/` into that worktree, since the new files are uncommitted and `HEAD` lacks them, and run every step from there, dependency install included. A fresh worktree is what a `/forge --work-dir` editor gets, so it is the real target, not a stand-in. When the proof is done, run `git worktree remove --force <scratch>/verify-proof`, then `ls -l` on every evidence path the proof printed. Those lines go into the hand-off reply. An evidence path `ls -l` cannot find fails this step.

## 6. Do not commit [Studio]

Do not commit, stage or push anything. The skill, its feature map and the `CLAUDE.md` line stay uncommitted, for the person to review and land as one PR.

## Hand-off

End with this reply, filled in, and nothing after it. Its last line is pstack's offer of the maintenance loop.

```
Verify skill: .claude/skills/verify-<app>/  (uncommitted, N files)
Proved: yes | NO: <step that failed> — <error line>
Feature driven: features/<file>.md via <entry point>
Evidence after cleanup: <absolute path>  <bytes>   (one line per file, from ls -l)
Stand-in gaps: none | <setup steps the proof's stand-in did that the real target will not>
Map: <n> features (<names>); not yet driven: <names>
Wired: CLAUDE.md line <n> | not wired: <why>
Next: review and land as one PR; keep it honest with /maintain-verification-skill (schedule: CLAUDE_CODE_USAGE.md).
```

A failed proof opens with `Proved: NO` and the files stay a draft. A repo that can't drive itself (an engine with no licence or headless driver, a docs-only repo) ends there, with the reason.

---

Adapted from `create-verification-skill` in pstack by Lauren Tan (`harness/pstack/claude-code/skills/create-verification-skill/` in `cursor/plugins`).

MIT License

Copyright (c) 2026 Lauren Tan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---
description: Save the in-flight thread to a durable note so you can /clear safely — or resume one
argument-hint: "[a note to add] | <slug to resume>"
---

A session is about to run out of room, or has already been cleared. `/handoff` writes the *state* of the work in flight to a small note in this repo, so the thread survives the conversation and can be picked back up from something precise instead of a long auto-summary.

The command lives in Studio; the note it writes belongs to whatever repo you are working in.

Pick the mode from `$ARGUMENTS`:

- **Save** — `/handoff [optional note]` writes (or overwrites) the handoff note for the thread in flight, then says in plain words that it is safe to `/clear`, and gives the exact command to resume.
- **Resume** — `/handoff <slug>` reads that thread's note and picks the work back up. If no slug is given and no thread is obviously in flight, list the open threads with their goal line and updated date, and ask which one.

If the argument matches an existing thread note, it is a resume. Otherwise it is a save, and the argument is a note to fold in.

## Where the note goes

Resolve the threads directory in this order, and say which one you used:

1. **The repo's own home for durable notes**, if its `CLAUDE.md` names one — a docs tree, a knowledge base, an Obsidian vault. Put the note where the project already keeps its records, in a `Threads/` folder there.
2. **A consuming repo** (Studio installed under `.studio/`): `.studio/threads/<slug>.md`.
3. **The Studio source repo** (a root `studio/` directory is present): `threads/<slug>.md`.

Slug is short kebab-case off the thread itself: `waiting-on-you-ledger`, `lobby-matchmaking`.

Match the repo's own note conventions — frontmatter shape, date format, tags, link syntax. If it has none, use the template below as written.

## Saving

**Check reality before you write.** Run `git status`, `git branch -vv`, `gh pr list`, and read the files you claim to have changed. Write from what you verified, not from what you remember happening in the conversation. A note recording what was *believed* is worse than none — it sends the next session confidently in the wrong direction.

```
---
type: thread
status: active
slug: <slug>
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# <Human Title>

## Goal
One sentence. What "done" looks like.

## Where this stands
- **Done:** what is finished AND verified, with the evidence (a PR number, a commit, a passing check)
- **In flight:** what is running or half-built right now, with exact paths/branches/run IDs
- **Next action:** the single next concrete step, specific enough to start cold

## Decisions made
Each decision with its reasoning, so it is not re-litigated in the next session.

## Blocked on
What is waiting, and on whom. If it is waiting on a person, say exactly what they have to do.

## Landmines
Facts learned the hard way this session that would cost real time to rediscover.
Example shape: "the scheduler refuses to run scripts outside its own scripts directory, so the job points at a launcher."

## Files & artifacts
Paths, branches, PRs, run directories. Enough to reopen everything without searching.
```

Rules for what goes in it:

- **State, not history.** Never narrate the conversation — no "we discussed", no "then I tried". Record where things *are*. The next session does not need the story.
- **Overwrite, don't append.** The note is a snapshot of now, not a log. Stale layers are exactly what this avoids.
- **Absolute dates only** (`2026-07-29`) — never "today" or "yesterday".
- **Be honest about what is unfinished.** If something is 80% done, name the missing 20% and why it stalled. That last stretch is what usually dies with the session.

Then say, in one short paragraph: what was saved, that it is safe to `/clear` now, and the literal command to resume — `/handoff <slug>`.

## Resuming

Read the note, then **re-verify before acting**. It records what was true when it was written; branches, PRs, and CI may have moved since. Check the same things a save checks, and say so plainly if reality has drifted from the note.

Give a short orientation — the goal, where it stands, the next action — then get on with it. Do not read the note back line by line.

## Closing a thread

Deleting the note is how a thread closes. When the work lands, remove it (or set `status: done` and move it to the repo's archive). A threads folder filling up with dead notes is its own mess.

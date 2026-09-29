# Claude Code hooks

There are no hooks left in this directory, and that is the point of the change that emptied it.

## Where `finish-check.py` went

`finish-check.py` was a Stop hook: it refuses the first stop of every turn with one paragraph asking
the assistant to re-read its own message for work it deferred that nothing is blocking, then lets the
second stop through. It now lives with the rest of Studio's source, as **`studio/finish_check.py`**.
Teaching the installer to copy it into each consuming repo at `.studio/source/finish_check.py` and
register it there is the next step in `specs/shipped-finish-check.md`, which also covers the override
paragraph a repo can supply in `.studio/finish-check.txt`. Until that step lands, the only copy that
runs anywhere is one someone points at by hand.

It moved because a hook kept here reached exactly one machine. The old rule was that nothing kept
here reached a consuming repo, so the hook had to be registered by hand in one person's global
settings; every other machine, Studio installed or not, ran without it. That rule no longer holds
for the finish-check.

## If you had the old hook wired up

**Repoint or remove it now, in the same sitting as pulling this change.** A symlink at
`~/.claude/hooks/finish-check.py`, or any global `hooks.Stop` entry naming that path, is now pointing
at a file that does not exist. A Stop hook that cannot start fails open: it stops running and it
stops *silently*, with nothing to tell you the check is gone. Point it at `studio/finish_check.py`
for now. Once the installer writes a per-repo entry, drop the global one rather than keeping both:
two registrations fire on the same stop and race each other's marker file.

## What this directory is still for

A hook belongs here only if it is specific to developing Studio itself and should never reach a
consuming repo. Anything worth having in every repo belongs in the shipped set instead, next to
`finish_check.py`.

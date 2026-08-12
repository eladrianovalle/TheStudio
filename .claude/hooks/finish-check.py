#!/usr/bin/env python3
"""Stop hook: one forced finish-check before Claude is allowed to end a turn.

The problem this exists for: Claude reliably stops a turn while work it just
described is still undone, hands the remainder to Adriano as a list, and that
list gets glossed over. Instructions in CLAUDE.md are read *before* the work,
when the loose ends are still hypothetical. This fires *after* the message is
written, when they are concrete and countable.

It blocks exactly once per turn, every turn. Blocking is the whole mechanism —
refusing the stop is what forces the re-read — so there is no silent mode, and
skipping turns that merely look clean would just be a keyword matcher deciding
instead of Claude. The only thing that can be kept small is the wording, so the
reason is one paragraph rather than a page.

The first stop is refused with that reason; Claude either does the remaining
work or confirms there is none, and the second stop goes through. Two
independent guards keep that from looping:

  1. `stop_hook_active` is true on stdin when this stop was itself caused by a
     stop hook, which is the harness telling us we already fired.
  2. A per-session marker file, written when we block and deleted when we let a
     stop through. This covers us if the field is ever absent or renamed.

Every invocation appends its raw stdin to finish-check.log (last 200 lines kept)
so the real payload shape can be inspected rather than guessed at.
"""

import json
import os
import sys
import time

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HOOKS_DIR, "state")
LOG_PATH = os.path.join(HOOKS_DIR, "finish-check.log")

# If a marker is older than this, treat it as debris from an abandoned turn
# rather than as "we already fired this turn".
MARKER_MAX_AGE_SECONDS = 3600

REASON = """FINISH-CHECK (automatic, not the user speaking). Re-read your message: anything you deferred that follows from your change or the ask, do now; delete observations that need no action from anyone; keep only genuine decisions and blockers, each with a recommendation. Rewording is not passing. If it is all done, stop again and this lets you through without comment."""


def log_payload(raw_text):
    """Append this invocation's stdin to the log, trimmed to the last 200 lines."""
    try:
        entry = "%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), raw_text.strip())
        existing = ""
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH) as log_file:
                existing = log_file.read()
        lines = (existing + entry).splitlines(keepends=True)[-200:]
        with open(LOG_PATH, "w") as log_file:
            log_file.writelines(lines)
    except OSError:
        pass  # logging must never be the reason a hook fails


def marker_path(session_id):
    return os.path.join(STATE_DIR, "%s.fired" % session_id)


def sweep_stale_markers():
    """Delete markers left behind by sessions that were abandoned mid-block.

    A marker is normally removed on the very next stop. One only survives if the
    session ended between the block and the retry, and past MARKER_MAX_AGE_SECONDS
    it is ignored anyway — so without this the directory grows forever.
    """
    try:
        names = os.listdir(STATE_DIR)
    except OSError:
        return
    cutoff = time.time() - MARKER_MAX_AGE_SECONDS
    for name in names:
        stale_path = os.path.join(STATE_DIR, name)
        try:
            if os.path.getmtime(stale_path) < cutoff:
                os.remove(stale_path)
        except OSError:
            pass


def already_fired_this_turn(path):
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return False
    return age < MARKER_MAX_AGE_SECONDS


def allow_stop(path):
    try:
        os.remove(path)
    except OSError:
        pass
    sys.exit(0)


def block_stop(path):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(path, "w") as marker:
            marker.write(str(time.time()))
    except OSError:
        # If we cannot record that we fired, we cannot guarantee we won't loop.
        # Letting the stop through is the safe failure.
        sys.exit(0)
    print(json.dumps({"decision": "block", "reason": REASON}))
    sys.exit(0)


def main():
    raw_text = sys.stdin.read()
    log_payload(raw_text)

    try:
        payload = json.loads(raw_text)
    except (ValueError, TypeError):
        payload = {}

    session_id = str(payload.get("session_id") or "unknown-session")
    path = marker_path(session_id)
    sweep_stale_markers()

    if payload.get("stop_hook_active"):
        allow_stop(path)
    if already_fired_this_turn(path):
        allow_stop(path)

    block_stop(path)


if __name__ == "__main__":
    main()

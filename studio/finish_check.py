#!/usr/bin/env python3
"""Stop hook: one forced finish-check before Claude is allowed to end a turn.

The problem this exists for: Claude reliably stops a turn while work it just
described is still undone, hands the remainder to the user as a list, and that
list gets glossed over. Instructions in CLAUDE.md are read *before* the work,
when the loose ends are still hypothetical. This fires *after* the message is
written, when they are concrete and countable.

It blocks exactly once per turn, every turn. Blocking is the whole mechanism --
refusing the stop is what forces the re-read -- so there is no silent mode, and
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

Two rules hold on every path through this file, because a hook whose job is to
never break a session has to fail open:

  * The exit status is always 0, and nothing is ever written to stderr. A Stop
    hook's stderr is surfaced to the user as an error, and blocking is expressed
    in stdout alone -- so a crash can never be mistaken for a deliberate block.
  * Anything that goes wrong lets the stop through rather than blocking it.

Zero Studio imports, deliberately: every Studio module can raise while being
imported, which would happen before any of our own error handling exists.
"""

import hashlib
import json
import os
import stat
import sys
import tempfile
import time

# Markers live in the system temp directory rather than beside this file: some
# repos track `.studio/`, and per-turn state written there would dirty their
# `git status` forever. The directory is per-user and private: on a shared Linux
# `/tmp`, a world-writable directory plus the predictable `unknown-session` digest
# would let anyone pre-create another user's marker and cost them the check. The
# name alone guarantees nothing -- anyone can create it first -- so
# `marker_dir_is_private` checks ownership and mode before a marker is trusted.
MARKER_DIR = os.path.join(
    tempfile.gettempdir(), "studio-finish-check-%d" % os.getuid()
)

# If a marker is older than this, treat it as debris from an abandoned turn
# rather than as "we already fired this turn".
MARKER_MAX_AGE_SECONDS = 600

# The repo's optional replacement for DEFAULT_REASON. Resolved from this file's
# own location -- once installed at `.studio/source/finish_check.py`, up two
# directories is `.studio/`, so the override is `.studio/finish-check.txt`. It is
# deliberately not resolved from the working directory (a hook runs from wherever
# the session happens to be, which is often not the project root) nor from an
# environment variable.
OVERRIDE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "finish-check.txt"
)

# The override is a paragraph, not a document. Anything larger is treated as a
# mistake and ignored in favour of the shipped wording.
OVERRIDE_MAX_BYTES = 4096

DEFAULT_REASON = """FINISH-CHECK (automatic, not the user speaking). Re-read your message: anything you deferred that follows from your change or the ask, do now; delete observations that need no action from anyone; keep only genuine decisions and blockers, each with a recommendation. Rewording is not passing. If it is all done, stop again and this lets you through without comment."""


def marker_path(session_id):
    """The marker file for one session: `<tempdir>/studio-finish-check/<sha256>.fired`.

    The session id arrives on stdin, so it is untrusted input being turned into a
    filesystem path. Hashing it is a security boundary, not tidiness: a raw value
    of `../../x` or `/etc/passwd` would let the delete on `stop_hook_active`, or
    the write on a block, reach outside the marker directory. A hex digest cannot
    contain a separator, so every marker is a direct child of that one directory
    whatever the payload says.
    """
    # The id may hold a NUL byte or arrive as thousands of characters; encoding it
    # with a replacement policy means neither can stop us producing a digest.
    digest = hashlib.sha256(str(session_id).encode("utf-8", "replace")).hexdigest()
    return os.path.join(MARKER_DIR, "%s.fired" % digest)


def marker_dir_is_private():
    """Create the marker directory if needed, then confirm nobody else controls it.

    `makedirs` with `exist_ok` accepts a directory someone else made first, so the
    `lstat` is what makes the per-user directory a defence: it must be a real
    directory, not a symlink to one, owned by us, with no group or other bits.
    """
    try:
        os.makedirs(MARKER_DIR, mode=0o700, exist_ok=True)
        info = os.lstat(MARKER_DIR)
    except OSError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) & 0o077 == 0
    )


def sweep_stale_markers():
    """Delete markers left behind by sessions that were abandoned mid-block.

    A marker is normally removed on the very next stop. One only survives if the
    session ended between the block and the retry, and past MARKER_MAX_AGE_SECONDS
    it is ignored anyway -- so without this the directory grows forever.
    """
    try:
        names = os.listdir(MARKER_DIR)
    except OSError:
        return
    cutoff = time.time() - MARKER_MAX_AGE_SECONDS
    for name in names:
        stale_path = os.path.join(MARKER_DIR, name)
        # `lstat`, so a dangling symlink is aged and swept like any other entry
        # instead of raising here and surviving every sweep.
        try:
            if os.lstat(stale_path).st_mtime < cutoff:
                os.remove(stale_path)
        except OSError:
            pass


def already_fired_this_turn(path):
    """Did we already block this turn?

    Age is the only evidence, which leaves one gap: if a session is interrupted
    between the block and the retry, the marker outlives the turn that wrote it,
    and the next turn's first stop spends it instead of firing. That turn goes
    unchecked. It fails open, which is the right direction, and closing it would
    mean pinning the marker to a turn identity the payload does not carry.
    """
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return False
    return age < MARKER_MAX_AGE_SECONDS


def reason_text():
    """The repo's override paragraph if it is usable, otherwise the shipped one.

    Absent, empty, unreadable and oversized all mean the same thing here: use the
    default. The override is the one sanctioned edit surface, and no way of
    getting it wrong may cost anyone the check itself.
    """
    try:
        if os.path.getsize(OVERRIDE_PATH) > OVERRIDE_MAX_BYTES:
            return DEFAULT_REASON
        with open(OVERRIDE_PATH, encoding="utf-8") as override_file:
            override = override_file.read()
    except (OSError, ValueError, UnicodeDecodeError):
        return DEFAULT_REASON
    return override if override.strip() else DEFAULT_REASON


def allow_stop(path):
    try:
        os.remove(path)
    except OSError:
        pass
    sys.exit(0)


def block_stop(path):
    try:
        # O_NOFOLLOW so a symlink left at this path is an error rather than a
        # write to wherever it points.
        flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW
        with os.fdopen(os.open(path, flags, 0o600), "w") as marker:
            marker.write(str(time.time()))
    except OSError:
        # If we cannot record that we fired, we cannot guarantee we won't loop.
        # Letting the stop through is the safe failure.
        sys.exit(0)
    print(json.dumps({"decision": "block", "reason": reason_text()}))
    sys.exit(0)


def main():
    raw_text = sys.stdin.read()

    try:
        payload = json.loads(raw_text)
    except (ValueError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        # `[]`, `"x"` and `3` all parse successfully, and `.get` on any of them
        # raises. Only a JSON object is a payload we can read.
        payload = {}

    session_id = str(payload.get("session_id") or "unknown-session")
    path = marker_path(session_id)
    if not marker_dir_is_private():
        # A marker in a directory someone else controls proves nothing, and one we
        # write there could be spent by them. Without a marker we cannot guarantee
        # we won't loop, so let the stop through.
        sys.exit(0)
    sweep_stale_markers()

    # `is True` rather than truthiness: a payload carrying the string "false" would
    # otherwise read as true and let the stop through. That direction is the safe one
    # -- every unhandled condition here allows the stop -- so this is about saying what
    # the field means, not about closing a hole.
    if payload.get("stop_hook_active") is True:
        allow_stop(path)
    if already_fired_this_turn(path):
        allow_stop(path)

    block_stop(path)


def run():
    """Run the hook and exit 0 no matter what happened.

    `SystemExit` derives from `BaseException`, so the deliberate `sys.exit(0)`
    calls inside `main` pass straight through this guard; everything else is
    swallowed, which allows the stop.
    """
    try:
        main()
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    run()

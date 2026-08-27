"""
Cross-repo Studio installer.

Copies Studio source, slash commands, workflows, config, and manifest into a
target project so that all slash commands (`/run-phase`, `/run-studio-phase`,
`/forge`, `/spec`, `/smoke`, `/unstale`, `/detest`, `/offload`,
`/studio-update`, `/studio-setup`, `/handoff`) work natively, including the
pause-and-ask collaboration protocol and the implementation-loop and
finding-verifier workflows.

Also injects coding principles (from docs/CODING_PRINCIPLES.md) into the
target project's CLAUDE.md using sentinel markers for idempotent updates.

Usage via run_phase.py:
    python run_phase.py init --target /path/to/project
    python run_phase.py check-install --target /path/to/project
    python run_phase.py update --target /path/to/project
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from config_loading import tomllib

# Files to copy from studio/ into .studio/source/
SOURCE_FILES = [
    "run_phase.py",
    "run_phase_roles.py",
    "role_overrides.py",
    "persona_overrides.py",
    "decision_points.py",
    "findings.py",
    "verifier.py",
    "question_mode.py",
    "scopes.py",
    "design_mandate.py",
    "cleanup.py",
    "rerun.py",
    "verdict.py",
    "install.py",
    "offload.py",
    "clarity.py",
    "setup.py",
    "impl_loop.py",
    "config_loading.py",
    "stats.py",
    "session.py",
    "studio.manifest.json",
    "validators/__init__.py",
    "validators/document_validator.py",
    "validators/code_validator.py",
    "integrations/__init__.py",
    "integrations/slack_digest.py",
    "config/scopes.toml",
    "config/studio_settings.toml",
    "config/implementation_loop.toml",
    "docs/STUDIO_BRIDGE_TEMPLATE.md",
    "docs/CODING_PRINCIPLES.md",
    "docs/SCOPES_GUIDE.md",
]

# Glob patterns for additional files
ROLE_PACK_GLOB = "role_packs/*.json"
PROMPT_DOC_GLOB = "docs/role_prompts/*.md"

# Slash commands to copy to {target}/.claude/commands/
# Commands Studio shipped once and no longer does. This list is the only way to spot one
# that was retired before the manifest pruning existed: the rename dropped the old name
# from SLASH_COMMANDS, the next manifest rebuild omitted it, and the file stayed on disk
# with nothing recording that Studio put it there (issue #95).
#
# Add a name here the same day you remove it from SLASH_COMMANDS, and never remove one:
# an entry costs a filesystem check, while a missing entry is a stale command that keeps
# answering with pre-rename behavior and nothing anywhere says so.
RETIRED_SLASH_COMMANDS = [
    "studio-implement.md",  # renamed to forge.md in 11086a4, 2026-07-08
]

SLASH_COMMANDS = [
    "run-phase.md",
    "run-studio-phase.md",
    "unstale.md",
    "studio-update.md",
    "detest.md",
    "offload.md",
    "studio-setup.md",
    "forge.md",
    "smoke.md",
    "spec.md",
    "handoff.md",
]

# Claude Code Workflows to copy to {target}/.claude/workflows/ (verbatim, like commands)
WORKFLOW_FILES = [
    "implementation-loop.js",
    "finding-verifier.js",
]

# Sentinels for CLAUDE.md injection: update replaces content between these markers
_SENTINEL_BEGIN = "<!-- STUDIO:CODING_PRINCIPLES:BEGIN -->"
_SENTINEL_END = "<!-- STUDIO:CODING_PRINCIPLES:END -->"


def _get_studio_root() -> Path:
    """Get the Studio source directory (the ``studio/`` dir this file lives in).

    Callers reach the repo root via ``.parent`` (e.g. for git metadata).
    """
    return Path(__file__).resolve().parent


def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_info(studio_root: Path) -> dict:
    """Get git commit and date from the studio source repo."""
    info: dict = {}
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H %aI"],
            cwd=studio_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(" ", 1)
            info["commit"] = parts[0]
            info["commit_date"] = parts[1] if len(parts) > 1 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return info


def _resolve_source_dir(
    target: Path, studio_dir: Optional[Path]
) -> Tuple[Path, Optional[str]]:
    """Resolve the live Studio source directory to compare/copy from.

    When ``check``/``update`` is invoked through the *installed snapshot*
    (``<target>/.studio/source/run_phase.py``), the default source root IS that
    snapshot, so comparing it against the installed ``MANIFEST.json`` compares
    the snapshot against itself and always reports "up to date", silently
    masking real upstream changes (see issue #20).

    To fix this, when the detected source root is the snapshot, fall back to the
    upstream ``source_path`` recorded in ``VERSION`` so we compare against the
    live source instead.

    Returns ``(source_dir, warning)``. ``warning`` is non-None when the live
    source could not be resolved, so the caller can surface it loudly instead of
    silently trusting the (possibly stale) snapshot.
    """
    if studio_dir is not None:
        # Explicit source (tests, or an upstream invocation that already knows
        # where the live source is), so trust it.
        return studio_dir, None

    root = _get_studio_root()
    snapshot = (target / ".studio" / "source").resolve()
    if root.resolve() != snapshot:
        # Running from a real upstream working copy, not the snapshot.
        return root, None

    upstream = (
        "Re-run from the upstream repo instead: "
        f"python studio/run_phase.py check-install --target {target}"
    )
    version_path = target / ".studio" / "VERSION"
    try:
        version = json.loads(version_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return root, (
            "running from the installed snapshot and VERSION is unreadable; "
            f"cannot compare against live source. {upstream}"
        )

    source_path = version.get("source_path")
    if not source_path:
        return root, (
            "running from the installed snapshot and VERSION has no "
            f"source_path; cannot compare against live source. {upstream}"
        )

    live = Path(source_path)
    if live.resolve() == snapshot or not (live / "run_phase.py").is_file():
        return root, (
            "running from the installed snapshot and the recorded source_path "
            f"({source_path}) is missing, moved, or points back to the "
            f"snapshot; cannot compare against live source. {upstream}"
        )
    return live, None


def _recorded_upstream_source(version_path: Path, snapshot: Path) -> Optional[Path]:
    """Return the upstream source dir recorded in an existing VERSION, but only if
    it is still a usable upstream: it exists, has ``run_phase.py``, and is NOT the
    target's own snapshot. Used to avoid overwriting a good pointer with a
    self-pointing one when (re)installing from the snapshot.
    """
    try:
        version = json.loads(version_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    sp = version.get("source_path")
    if not sp:
        return None
    p = Path(sp)
    if p.resolve() == snapshot or not (p / "run_phase.py").is_file():
        return None
    return p


def _git_out(repo: Path, *args: str) -> Optional[str]:
    """Run a git command in ``repo`` and return its stripped stdout.

    Returns ``None`` if git isn't available or the command fails, so callers can
    treat "can't tell" the same as "not a git repo" and fall back safely.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return None
    return result.stdout.strip()


def _default_branch_ref(repo: Path) -> Optional[str]:
    """Resolve the branch that holds the *finished* Studio source in ``repo``.

    Prefers a local ``main``/``master``, then the same on ``origin``. Returns
    ``None`` when none resolve, so the caller falls back to reading the working
    tree as-is.
    """
    for ref in ("main", "master"):
        if _git_out(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{ref}") is not None:
            return ref
    for ref in ("origin/main", "origin/master"):
        if _git_out(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{ref}") is not None:
            return ref
    return None


@dataclass(frozen=True)
class SourceStaleness:
    """Whether a Studio source checkout is behind its own git remote.

    Produced by ``_source_staleness``. Best-effort by design: when staleness
    can't be determined (offline, no remote, detached HEAD, not a git repo),
    ``is_stale`` is False and ``reason`` says why, so callers fall back to
    today's behavior instead of blocking on a guess.
    """
    is_stale: bool
    behind: int
    remote_ref: Optional[str]
    fetched: bool
    reason: Optional[str]


def _default_branch_ref_local(repo: Path) -> Optional[str]:
    """Return the LOCAL default branch name ('main' or 'master') in ``repo``.

    This is the local-only half of ``_default_branch_ref``. It deliberately does
    NOT fall back to ``origin/main``: staleness detection has to compare the local
    branch against origin, and if the local ref resolved to origin the two sides
    would be identical and always look "even". Returns None when neither local
    branch exists (detached HEAD with no default branch, or not a git repo).
    """
    for ref in ("main", "master"):
        if _git_out(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{ref}") is not None:
            return ref
    return None


def _git_fetch(repo: Path, branch: str, *, timeout: float) -> bool:
    """Fetch ``origin``'s ``branch`` into ``repo``, bounded by ``timeout`` seconds.

    A small, network-bounded sibling to ``_git_out``. Returns True when the fetch
    succeeds and False on ANY failure — a non-zero git exit, git missing, or the
    fetch running past ``timeout``. It never raises, so an offline or slow remote
    degrades to "couldn't fetch" rather than crashing the update check.

    Kept separate from ``_git_out`` on purpose: that helper is called all over
    with ``check=True`` and no timeout, and giving it a network timeout would
    ripple to every caller.
    """
    try:
        subprocess.run(
            ["git", "-C", str(repo), "fetch", "origin", branch],
            capture_output=True, text=True, check=True, timeout=timeout,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    return True


def _source_staleness(
    repo: Path, *, fetch: bool = True, timeout: float = 5.0
) -> SourceStaleness:
    """Report whether ``repo``'s local default branch is behind its origin.

    Best-effort and NEVER raises. The steps: resolve the local default branch,
    confirm ``origin/<branch>`` exists, optionally fetch origin (bounded by
    ``timeout``), then count how far local is behind origin.

    ``is_stale`` is True ONLY when local is strictly *behind* origin. A checkout
    that is merely *ahead* (unpushed local work) is not stale and must not be
    flagged. Every "can't tell" case — no local default branch, no origin
    tracking ref, or a comparison that fails — returns ``is_stale=False`` with a
    ``reason`` set, so the caller proceeds exactly as it would without staleness
    detection.
    """
    branch = _default_branch_ref_local(repo)
    if branch is None:
        return SourceStaleness(
            is_stale=False, behind=0, remote_ref=None, fetched=False,
            reason="no local main/master branch (detached HEAD or not a git repo)",
        )

    remote_ref = f"origin/{branch}"

    # Fetch FIRST, then look for the tracking ref. A remote that was configured
    # by hand but never fetched has no refs/remotes/origin/<branch> yet; checking
    # before fetching would bow out as "origin not configured" on exactly the
    # unfetched-origin case this detection exists to catch. The fetch creates the
    # ref; if it fails (offline), we fall back to whatever cached ref exists.
    fetched = False
    if fetch:
        fetched = _git_fetch(repo, branch, timeout=timeout)

    origin_ref_exists = _git_out(
        repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote_ref}"
    ) is not None
    if not origin_ref_exists:
        return SourceStaleness(
            is_stale=False, behind=0, remote_ref=None, fetched=fetched,
            reason=f"no {remote_ref} tracking ref (origin not configured or unreachable)",
        )

    # `--left-right --count A...B` prints "<left>\t<right>": left = commits only
    # on A (local, i.e. ahead), right = commits only on B (origin, i.e. behind).
    counts = _git_out(
        repo, "rev-list", "--left-right", "--count", f"{branch}...{remote_ref}"
    )
    if counts is None:
        return SourceStaleness(
            is_stale=False, behind=0, remote_ref=remote_ref, fetched=fetched,
            reason=f"could not compare {branch} against {remote_ref}",
        )

    fields = counts.split()
    behind = int(fields[1]) if len(fields) == 2 else 0

    reason = None
    if fetch and not fetched:
        reason = f"could not fetch {remote_ref}; compared against cached refs"

    return SourceStaleness(
        is_stale=behind > 0,
        behind=behind,
        remote_ref=remote_ref,
        fetched=fetched,
        reason=reason,
    )


def _source_auto_pull_enabled(source_dir: Path) -> bool:
    """Return whether the SOURCE repo opted into auto fast-forward.

    Reads ``[update] auto_pull_source`` from the source repo's own
    ``.studio/update.toml``. LOCATION IS LOAD-BEARING: the config is read from the
    SOURCE repo's top-level ``.studio/``, found via ``git rev-parse
    --show-toplevel`` on ``source_dir`` — NOT ``get_artifact_root()`` (the consumer
    repo) and NOT ``get_studio_root()`` (the installed snapshot). One line on the
    developer's source checkout covers every consumer on that machine.

    Best-effort and NEVER raises: returns False on a non-git dir, a missing file,
    a missing ``[update]`` table, a missing key, or malformed TOML.
    """
    top = _git_out(source_dir, "rev-parse", "--show-toplevel")
    if top is None:
        return False
    config_path = Path(top) / ".studio" / "update.toml"
    if not config_path.is_file():
        return False
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    section = data.get("update")
    return bool(section.get("auto_pull_source", False)) if isinstance(section, dict) else False


@dataclass(frozen=True)
class SourcePull:
    """Outcome of trying to fast-forward a Studio source checkout to its origin.

    Produced by ``_fast_forward_source``. ``pulled`` is True only when the
    fast-forward actually happened; on any skip ``reason`` says why and nothing
    was mutated.
    """
    pulled: bool               # did the fast-forward happen
    reason: Optional[str]      # why it was skipped (None on success)
    new_head: Optional[str]    # short sha the source now points at (None if not pulled)


def _fast_forward_source(source_dir: Path, staleness: SourceStaleness) -> SourcePull:
    """Fast-forward ``source_dir``'s local default branch to its origin, if safe.

    Performs the fast-forward ONLY when every precondition below holds, in order;
    on any failure it returns ``SourcePull(pulled=False, reason=...)`` and mutates
    nothing. Best-effort and NEVER raises. It reuses ``staleness`` (origin was
    already fetched and ``behind`` already counted by ``_source_staleness``) and
    does NO extra network work.
    """
    # (1) The source must have a LOCAL default branch to fast-forward.
    branch = _default_branch_ref_local(source_dir)
    if branch is None:
        return SourcePull(False, "source has no local default branch", None)

    # (2) LOAD-BEARING SAFETY GUARD: HEAD must actually be that default branch.
    # staleness.is_stale is computed on local main vs origin/main regardless of
    # where HEAD currently sits, so a detached HEAD (mid-rebase) or a feature
    # branch could be "stale" while a blind `merge --ff-only origin/main` would
    # move the wrong ref. Refuse unless HEAD IS the default branch.
    current = _git_out(source_dir, "rev-parse", "--abbrev-ref", "HEAD")
    if current != branch:
        where = current if current is not None else "a detached HEAD"
        return SourcePull(
            False, f"source HEAD is on {where}, not the default branch {branch}", None
        )

    # (3) The working tree must be clean. Kept deliberately dumb — any output from
    # status --porcelain means skip. Gitignored clutter (.studio/, output/, ...)
    # never shows, so ordinary developer state doesn't falsely block the ff.
    if _git_out(source_dir, "status", "--porcelain"):
        return SourcePull(False, "source working tree has uncommitted changes", None)

    # (4) The move must be a true fast-forward. _git_out runs with check=True and
    # returns None on a non-zero exit; git refuses a non-ff (diverged/ahead, or a
    # lingering MERGE_HEAD) and leaves HEAD and the tree untouched, so a refused
    # ff is a guaranteed no-op.
    remote_ref = staleness.remote_ref
    if _git_out(source_dir, "merge", "--ff-only", remote_ref) is None:
        return SourcePull(
            False, f"source has diverged from {remote_ref} (not fast-forwardable)", None
        )

    new_head = _git_out(source_dir, "rev-parse", "--short", "HEAD")
    return SourcePull(True, None, new_head)


UPDATE_CHECK_CACHE = "update-check.json"
UPDATE_CHECK_SENTINEL = "update-check.off"
UPDATE_CHECK_TTL_SECONDS = 24 * 3600
UPDATE_ADDITIONAL_CONTEXT = (
    "A Studio update is available upstream. Tell the user: run /studio-update "
    "to refresh the installed Studio copy."
)


@dataclass(frozen=True)
class UpdateCheck:
    """Whether a consuming repo's installed Studio snapshot is behind upstream.

    Produced by ``compute_update_check``. Best-effort: every branch that can't
    answer cleanly (opted out, offline, no source on this machine, not a git
    repo, already current) returns ``should_notify=False`` with a ``reason``,
    so the caller degrades to silence instead of nudging on a guess.
    """
    should_notify: bool
    reason: Optional[str]


def _load_update_cache(target: Path) -> Dict:
    """Read the update-check cache under ``<target>/.studio/update-check.json``.

    Returns an empty dict when the file is missing or corrupt, so the caller
    treats a bad cache the same as a cold start. Never raises.
    """
    cache_path = target / ".studio" / UPDATE_CHECK_CACHE
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Discard a hand-edited/corrupt cache whose fields are the wrong type, so the
    # TTL math (``now - last_check``) and the SHA compares can't raise later. A bad
    # cache then behaves exactly like a cold start rather than wedging the check.
    if not isinstance(data.get("last_check"), (int, float)):
        return {}
    # Commit fields may be a SHA string or None (e.g. notified_commit before any
    # notification); reject only an outright wrong type (list/dict/number) that a
    # hand-edit could introduce.
    for key in ("source_commit", "notified_commit"):
        if key in data and not isinstance(data[key], (str, type(None))):
            return {}
    return data


def _write_update_cache(target: Path, cache: Dict) -> None:
    """Write the update-check cache. Swallows any write failure.

    The check is advisory and must never fail a session, so a read-only
    filesystem or a missing ``.studio`` directory degrades to "cache not
    written" rather than raising.
    """
    cache_path = target / ".studio" / UPDATE_CHECK_CACHE
    try:
        cache_path.write_text(
            json.dumps(cache, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        pass


def compute_update_check(
    target: Path, *, now: Optional[float] = None, fetch_timeout: float = 5.0
) -> UpdateCheck:
    """Decide whether to nudge that ``target``'s installed Studio is behind upstream.

    Best-effort and NEVER raises. Compares the commit the snapshot was installed
    from (``.studio/VERSION``) against the current ``origin/<branch>`` HEAD of the
    live Studio source it was installed from. A network fetch happens at most once
    per ``UPDATE_CHECK_TTL_SECONDS`` (governed by the cache); everything else is
    read live so running ``/studio-update`` clears the nudge immediately.

    Every "can't tell" branch returns ``should_notify=False`` with a descriptive
    ``reason``. ``now`` is injectable for deterministic TTL tests.
    """
    now = now if now is not None else time.time()

    studio_dir = target / ".studio"

    # Opt-out: a one-bit sentinel file silences the check entirely.
    if (studio_dir / UPDATE_CHECK_SENTINEL).exists():
        return UpdateCheck(should_notify=False, reason="disabled")

    # Installed commit: the SHA the snapshot was installed from.
    try:
        version = json.loads(
            (studio_dir / "VERSION").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError, ValueError):
        return UpdateCheck(should_notify=False, reason="VERSION unreadable")
    installed_commit = version.get("commit")
    if not installed_commit or installed_commit == "unknown":
        return UpdateCheck(
            should_notify=False, reason="installed commit missing or unknown"
        )

    # Resolve the live upstream source. Any warning means the source isn't on
    # this machine (teammate clone), moved, or points back at the snapshot —
    # the same resolution check-install/update use.
    source_dir, warning = _resolve_source_dir(target, None)
    if warning:
        return UpdateCheck(should_notify=False, reason=warning)

    branch = _default_branch_ref_local(source_dir) or "main"
    remote_ref = f"refs/remotes/origin/{branch}"

    cache = _load_update_cache(target)
    fresh = (
        "source_commit" in cache
        and now - cache.get("last_check", 0) < UPDATE_CHECK_TTL_SECONDS
    )
    if fresh:
        source_commit = cache["source_commit"]
        did_fetch = False
    else:
        _git_fetch(source_dir, branch, timeout=fetch_timeout)
        did_fetch = True
        source_commit = _git_out(
            source_dir, "rev-parse", "--verify", "--quiet", remote_ref
        )

    # No origin ref: offline first run, no origin, not a git repo, detached.
    # Write no cache so the next online session retries.
    if source_commit is None:
        return UpdateCheck(
            should_notify=False,
            reason=f"could not resolve {remote_ref} (offline or no origin)",
        )

    update_available = source_commit != installed_commit
    should_notify = update_available and source_commit != cache.get(
        "notified_commit"
    )

    _write_update_cache(
        target,
        {
            "last_check": now if did_fetch else cache.get("last_check", now),
            "source_commit": source_commit,
            "notified_commit": (
                source_commit if should_notify else cache.get("notified_commit")
            ),
        },
    )

    reason = None if should_notify else (
        "up to date" if not update_available else "already notified"
    )
    return UpdateCheck(should_notify=should_notify, reason=reason)


# Substring that identifies OUR SessionStart hook entry among any others the user
# has configured. The check-updates subcommand name is stable and unique enough to
# recognize our command on re-install without matching anyone else's hook.
_HOOK_MARKER = "check-updates"


def _hook_command() -> str:
    """The exact shell command our SessionStart hook runs.

    Uses the absolute ``sys.executable`` captured at install time, not a bare
    ``python``: on a stock macOS only ``python3`` exists, so ``python`` is
    ``command not found`` and the check silently never runs — for exactly the one
    user (the installer) it targets. Baking the resolving interpreter also settles
    the ``python`` vs ``python3`` question outright.

    Both the interpreter and the script path are absolute (the script via
    ``$CLAUDE_PROJECT_DIR``): Claude Code runs hook commands from the session's
    working directory, which may be a subdirectory of the repo, not the project
    root. A cwd-relative script path would make Python exit 2 ("can't open file")
    and surface a hook error at session start, breaking the always-exit-0 contract.
    Both paths are quoted so a space in either doesn't split the command.
    """
    return (
        f'"{sys.executable}" "$CLAUDE_PROJECT_DIR/.studio/source/run_phase.py" '
        f'check-updates --target "$CLAUDE_PROJECT_DIR"'
    )


def _install_sessionstart_hook(target: Path, *, enabled: bool) -> None:
    """Merge (or remove) our SessionStart update-check hook in the target.

    Writes to ``<target>/.claude/settings.local.json`` — the per-user, gitignored
    settings file, NOT the shared ``settings.json``. The check is machine-local
    (both the source path and the interpreter path are absolute to the installer's
    box), so committing the hook would inflict an unresolvable command on every
    teammate.

    Best-effort and NEVER raises. Identifies our own entry by the ``check-updates``
    substring so it stays idempotent across re-installs and refreshes the command
    (interpreter/version) on re-install. Every other key and hook in the file is
    left untouched. If the file exists but doesn't hold a JSON object, prints a
    one-line warning and returns rather than clobbering a file it can't read.

    When ``enabled`` is False (``--no-hook`` or the opt-out sentinel), any existing
    entry of ours is removed and none is added.
    """
    settings_path = target / ".claude" / "settings.local.json"

    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            print(
                f"  WARNING: {settings_path} is not a JSON object; "
                "left it untouched and skipped the update-check hook."
            )
            return
    else:
        data = {}

    # Guard the fields the same way as the top-level object: if the user's file
    # already has a `hooks` that isn't an object, or a `SessionStart` that isn't a
    # list, don't clobber their unexpected shape — warn and leave it be. (Without
    # this, `hooks.setdefault(...)` on a list or iterating a dict `SessionStart`
    # would raise out of install_studio, despite the never-raises contract.)
    if "hooks" in data and not isinstance(data["hooks"], dict):
        print(
            f"  WARNING: {settings_path} has a non-object 'hooks'; "
            "left it untouched and skipped the update-check hook."
        )
        return
    hooks = data.setdefault("hooks", {})
    if "SessionStart" in hooks and not isinstance(hooks["SessionStart"], list):
        print(
            f"  WARNING: {settings_path} has a non-list 'hooks.SessionStart'; "
            "left it untouched and skipped the update-check hook."
        )
        return
    entries = hooks.setdefault("SessionStart", [])

    # Find our own entry (the group whose command contains the marker).
    our_entry = None
    for entry in entries:
        commands = (inner.get("command", "") for inner in entry.get("hooks", []))
        if any(_HOOK_MARKER in command for command in commands):
            our_entry = entry
            break

    if our_entry is None and not enabled:
        return  # Nothing of ours, and none wanted: leave the file as-is.

    # Remove any stale entry of ours, then re-add fresh when enabled. Re-adding
    # (rather than editing in place) refreshes the command in one path — the
    # interpreter or source path can change across updates.
    if our_entry is not None:
        entries.remove(our_entry)
    if enabled:
        entries.append(
            {"hooks": [{"type": "command", "command": _hook_command()}]}
        )

    # Drop now-empty containers we own, so we leave no empty scaffolding behind.
    if not entries:
        hooks.pop("SessionStart", None)
    if not hooks:
        data.pop("hooks", None)

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        settings_path.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
    except OSError:
        pass


@contextmanager
def _source_at_default_branch(
    studio_dir: Path, enabled: bool, override_ref: Optional[str] = None
) -> Iterator[Tuple[Path, Optional[str]]]:
    """Yield ``(source_dir, note)`` to read Studio source from.

    When ``enabled`` and ``studio_dir`` is inside a git working copy with a
    resolvable default branch, materialize that branch's *committed* tree in a
    throwaway detached worktree and yield the matching source dir inside it — so
    ``check``/``update`` always read the finished ``main`` version, never
    whatever branch the source checkout happens to be parked on (or its
    uncommitted edits). This is the backstop that keeps a work-in-progress
    branch from leaking into other projects' update checks.

    ``override_ref`` lets a caller that already knows the source is stale read a
    specific ref instead (e.g. ``origin/main``). When given, the clean-tree fast
    path is skipped — the whole point is to read something *other* than the
    checked-out local tree — and ``note`` explains that the source was read from
    origin instead of the behind-by-N local branch.

    Falls back to ``studio_dir`` unchanged (``note`` = None) when disabled, not a
    git repo, the branch can't be resolved, or (with no override) the checkout is
    already sitting on that branch's commit with a clean tree. ``note`` is a short
    human line naming the ref that was read in place of the checkout; None when
    nothing was bypassed.
    """
    if not enabled:
        yield studio_dir, None
        return

    top = _git_out(studio_dir, "rev-parse", "--show-toplevel")
    repo = Path(top) if top else None
    if repo is None:
        yield studio_dir, None
        return

    # With an override the caller has already decided which ref to read (the
    # stale-source case reads origin/main); otherwise resolve the local default branch.
    ref = override_ref if override_ref is not None else _default_branch_ref(repo)
    if ref is None:
        yield studio_dir, None
        return

    # Fast path: already on the default branch's commit with a clean tree, so the
    # working tree already IS the finished source. Skip the worktree churn. An
    # override ref is by definition not the checked-out tree, so never fast-path it.
    if override_ref is None:
        head = _git_out(repo, "rev-parse", "HEAD")
        if head is not None and head == _git_out(repo, "rev-parse", ref) and not _git_out(repo, "status", "--porcelain"):
            yield studio_dir, None
            return

    try:
        rel = studio_dir.resolve().relative_to(repo.resolve())
    except ValueError:
        yield studio_dir, None
        return

    current = _git_out(repo, "rev-parse", "--abbrev-ref", "HEAD")
    tmp = Path(tempfile.mkdtemp(prefix="studio-src-"))
    worktree = tmp / "wt"
    added = False
    try:
        # --detach checks out the commit, not the branch, so it works even when
        # `main` is already checked out in another worktree.
        if _git_out(repo, "worktree", "add", "--detach", str(worktree), ref) is None:
            yield studio_dir, None
            return
        added = True
        note = None
        if override_ref is not None:
            note = f"read Studio source from '{ref}' — your local checkout is behind it"
        elif current and current != ref:
            note = f"read Studio source from '{ref}' (the source checkout is on '{current}')"
        yield worktree / rel, note
    finally:
        if added:
            _git_out(repo, "worktree", "remove", "--force", str(worktree))
        shutil.rmtree(tmp, ignore_errors=True)


def _collect_source_files(studio_dir: Path) -> List[Path]:
    """Collect all source files to install (relative to studio/)."""
    files: List[Path] = []

    # Explicit files
    for f in SOURCE_FILES:
        path = studio_dir / f
        if path.exists():
            files.append(Path(f))

    # Glob patterns
    for pattern in [ROLE_PACK_GLOB, PROMPT_DOC_GLOB]:
        for path in sorted(studio_dir.glob(pattern)):
            files.append(path.relative_to(studio_dir))

    return files



def _claude_manifest_keys(studio_dir: Path) -> List[str]:
    """Manifest keys for the verbatim ``.claude/`` commands + workflows.

    These install OUTSIDE ``.studio/source/`` (into ``.claude/commands/`` and
    ``.claude/workflows/``), so they're keyed by their repo-root-relative install
    path (``.claude/commands/run-phase.md``) to distinguish them from source files
    (keyed bare, relative to ``.studio/source/``). Including them in the manifest
    is what lets the clobber guard notice local edits to a command or workflow.
    """
    repo_root = studio_dir.parent
    keys: List[str] = []
    for name in SLASH_COMMANDS:
        if (repo_root / ".claude" / "commands" / name).is_file():
            keys.append(f".claude/commands/{name}")
    for name in WORKFLOW_FILES:
        if (repo_root / ".claude" / "workflows" / name).is_file():
            keys.append(f".claude/workflows/{name}")
    return keys


def _retired_claude_files(extra: List[str]) -> List[str]:
    """The installed commands/workflows Studio has stopped shipping.

    ``extra`` is every manifest key that no longer exists in the source. This
    narrows it to the verbatim ``.claude/`` files, which are the ones ``update``
    removes: a command that was renamed (``/studio-implement`` became ``/forge``)
    otherwise lingers forever beside its replacement, so the project offers two
    commands for one job and the stale one is the pre-rename behavior.

    Being in the manifest is what makes removal safe: the manifest only records
    files this installer wrote. A command the project author wrote by hand was
    never in it, so it can never be deleted here.

    Deliberately limited to ``.claude/``. Retired files under ``.studio/source/``
    are left alone — that snapshot is Studio's own tree, a leftover module there
    is inert, and removing files from it is a separate decision.

    **The boundary, because it reads wider than it is:** this deletes what the manifest
    still records. A file that fell out of the manifest *before* pruning existed is
    invisible here, permanently — renaming ``/studio-implement`` to ``/forge`` dropped the
    old name from SLASH_COMMANDS, so the next rebuild simply omitted it and left the file
    on disk with nothing behind it. ``_historical_orphans`` reports that class; it cannot
    be fixed here without the manifest entry this function is built on (issue #95).
    """
    return sorted(key for key in extra if key.startswith(".claude/"))


def _historical_orphans(target: Path, manifest: dict) -> List[str]:
    """Commands Studio used to ship that are still on disk with no manifest entry.

    The prune above can only remove what the manifest records, so a command retired
    before pruning existed is invisible to it forever. Those files keep working as slash
    commands and ``check-install`` called the repo up to date, so a user could invoke
    pre-rename behavior for weeks with nothing saying it was stale — silent in both
    directions, which is what makes it worth a check of its own.

    Matching on RETIRED_SLASH_COMMANDS rather than on "every ``.claude/commands/*.md``
    Studio does not currently ship" is the whole safety argument. The second reading would
    sweep up the project's own hand-written commands, which is precisely what the manifest
    normally protects and exactly what we have lost here. A name Studio itself retired is
    the one signal available that does not need the manifest.

    Reports, never deletes. A project may legitimately have written its own command at a
    name Studio once used, and no evidence available here separates that from a leftover.
    """
    recorded = set(manifest)
    found = []
    for name in RETIRED_SLASH_COMMANDS:
        key = f".claude/commands/{name}"
        if key not in recorded and (target / key).is_file():
            found.append(key)
    return sorted(found)


def _manifest_source_path(studio_dir: Path, key: str) -> Path:
    """Map a manifest key to its file in the live source tree."""
    if key.startswith(".claude/"):
        return studio_dir.parent / key
    return studio_dir / key


def _manifest_installed_path(target: Path, key: str) -> Path:
    """Map a manifest key to its installed file in the target."""
    if key.startswith(".claude/"):
        return target / key
    return target / ".studio" / "source" / key


def _build_manifest(
    manifest_keys: List[str],
    studio_dir: Path,
) -> Dict[str, str]:
    """Build install manifest: {key: sha256}.

    Keys are resolved to their live-source path via ``_manifest_source_path`` so
    source files and the verbatim ``.claude/`` files share one flat manifest.
    """
    manifest: Dict[str, str] = {}
    for key in manifest_keys:
        full = _manifest_source_path(studio_dir, str(key))
        if full.is_file():
            manifest[str(key)] = _sha256(full)
    return manifest


def _build_principles_block(studio_dir: Path) -> str:
    """Read CODING_PRINCIPLES.md and wrap in sentinel markers for CLAUDE.md injection.

    The content is re-headed as a ## section (not #) so it sits naturally inside
    an existing CLAUDE.md that starts with a top-level heading.
    """
    src = studio_dir / "docs" / "CODING_PRINCIPLES.md"
    raw = src.read_text(encoding="utf-8")
    # Downgrade headings: # → ##, ## → ###  (so it nests under CLAUDE.md's # heading)
    lines = []
    for line in raw.splitlines():
        if line.startswith("## "):
            lines.append("#" + line)  # ## → ###
        elif line.startswith("# "):
            lines.append("#" + line)  # # → ##
        else:
            lines.append(line)
    body = "\n".join(lines)
    return f"{_SENTINEL_BEGIN}\n{body}\n{_SENTINEL_END}"


def _principles_block_stale(target: Path, studio_dir: Path) -> bool:
    """Return True when the target's CLAUDE.md coding-principles block is missing
    or behind the current Studio template.

    The block is injected between sentinel markers at install time and is NOT part
    of the file manifest, so a plain checksum diff never notices when Studio's
    principles move ahead (e.g. a new principle is added upstream). This lets
    check/update spot a stale block and refresh it, while leaving the rest of
    CLAUDE.md — the user's own project notes — untouched.

    Only flags a CLAUDE.md that already exists: a routine update check won't
    resurrect a file the user deliberately removed.
    """
    claude_md = target / "CLAUDE.md"
    if not claude_md.is_file():
        return False
    try:
        content = claude_md.read_text(encoding="utf-8")
        expected = _build_principles_block(studio_dir)
    except OSError:
        return False
    if _SENTINEL_BEGIN not in content or _SENTINEL_END not in content:
        # Installed repo whose CLAUDE.md lost (or never had) the block: refresh it.
        return True
    start = content.index(_SENTINEL_BEGIN)
    end = content.index(_SENTINEL_END) + len(_SENTINEL_END)
    return content[start:end] != expected


def _inject_principles_into_claude_md(target: Path, studio_dir: Path) -> None:
    """Inject or update the coding principles block in the target's CLAUDE.md.

    - If CLAUDE.md doesn't exist, creates it with just the principles block.
    - If it exists and already has sentinels, replaces the block in place.
    - If it exists without sentinels, prepends the block after the first heading
      (or at the top if there's no heading).
    """
    block = _build_principles_block(studio_dir)
    claude_md = target / "CLAUDE.md"

    if not claude_md.exists():
        claude_md.write_text(block + "\n", encoding="utf-8")
        print(f"  Created {claude_md} (Studio coding principles only — add your project notes).")
        return

    content = claude_md.read_text(encoding="utf-8")

    if _SENTINEL_BEGIN in content:
        # Replace existing block
        before = content[: content.index(_SENTINEL_BEGIN)]
        after = content[content.index(_SENTINEL_END) + len(_SENTINEL_END) :]
        claude_md.write_text(before + block + after, encoding="utf-8")
    else:
        # Insert after the first heading line (# ...) or at the top
        lines = content.split("\n")
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("# ") and not line.startswith("## "):
                insert_idx = i + 1
                # Skip blank lines after heading
                while insert_idx < len(lines) and lines[insert_idx].strip() == "":
                    insert_idx += 1
                break

        lines.insert(insert_idx, block + "\n")
        claude_md.write_text("\n".join(lines), encoding="utf-8")


def install_studio(
    target: Path,
    studio_dir: Optional[Path] = None,
    source_path_override: Optional[Path] = None,
    install_hook: bool = True,
) -> Path:
    """Install Studio into a target project directory.

    Creates:
        {target}/.studio/source/     : Studio Python source + config
        {target}/.claude/commands/    : Slash commands (verbatim, use .studio/source/ paths)
        {target}/.claude/workflows/   : Claude Code workflows (verbatim, resolve .studio/source/ at run time)
        {target}/.studio/VERSION      : Version info
        {target}/.studio/MANIFEST.json : Install manifest with checksums

    ``source_path_override`` records a different upstream in VERSION than the dir
    files were copied from. Used when ``update`` copies from a throwaway worktree
    of ``main`` (see ``_source_at_default_branch``): the files come from the temp
    worktree, but VERSION must still point at the real, durable upstream so the
    next update knows where to look — never at the temp path, which is gone by then.

    Returns the .studio directory path.
    """
    if studio_dir is None:
        studio_dir = _get_studio_root()

    target = Path(target).resolve()
    dot_studio = target / ".studio"
    source_dest = dot_studio / "source"
    commands_dest = target / ".claude" / "commands"

    # Collect files
    source_files = _collect_source_files(studio_dir)

    # Copy source files (skip if src and dst are the same file,
    # which happens when update is run from the installed copy)
    for rel in source_files:
        src = studio_dir / rel
        dst = source_dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and src.samefile(dst):
            continue
        shutil.copy2(src, dst)

    # Copy slash commands verbatim (they use .studio/source/ paths directly)
    commands_dest.mkdir(parents=True, exist_ok=True)
    commands_src = studio_dir.parent / ".claude" / "commands"
    for cmd_name in SLASH_COMMANDS:
        src = commands_src / cmd_name
        if not src.exists():
            continue
        dst = commands_dest / cmd_name
        if dst.exists() and src.samefile(dst):
            continue
        shutil.copy2(src, dst)

    # Copy Claude Code workflows verbatim (they resolve .studio/source/ paths at run time)
    workflows_dest = target / ".claude" / "workflows"
    workflows_src = studio_dir.parent / ".claude" / "workflows"
    for wf_name in WORKFLOW_FILES:
        src = workflows_src / wf_name
        if not src.exists():
            continue
        workflows_dest.mkdir(parents=True, exist_ok=True)
        dst = workflows_dest / wf_name
        if dst.exists() and src.samefile(dst):
            continue
        shutil.copy2(src, dst)

    # Ensure output and knowledge dirs exist
    (dot_studio / "output").mkdir(parents=True, exist_ok=True)
    (dot_studio / "knowledge").mkdir(parents=True, exist_ok=True)

    # Build and write manifest (source files + verbatim .claude/ commands & workflows)
    manifest_keys = [str(p) for p in source_files] + _claude_manifest_keys(studio_dir)
    manifest = _build_manifest(manifest_keys, studio_dir)
    manifest_path = dot_studio / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Write VERSION
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    git = _git_info(studio_dir.parent)
    version_path = dot_studio / "VERSION"
    # Never record a source_path that points at the target's own snapshot: it would
    # make every future snapshot-based check compare the snapshot against itself
    # (silent "up to date") and leave `update` with no breadcrumb back to upstream.
    # When (re)installing FROM the snapshot (e.g. `init` run inside an installed
    # repo), preserve a previously-recorded upstream pointer instead of clobbering it.
    source_path = studio_dir
    if source_path_override is not None:
        source_path = source_path_override
    elif studio_dir.resolve() == source_dest.resolve():
        prior = _recorded_upstream_source(version_path, source_dest.resolve())
        if prior is not None:
            source_path = prior
    version_info = {
        "installed_at": now,
        "source_path": str(source_path),
        "commit": git.get("commit", "unknown"),
        "commit_date": git.get("commit_date", ""),
        "file_count": len(manifest),
    }
    version_path.write_text(
        json.dumps(version_info, indent=2), encoding="utf-8"
    )

    # Inject coding principles into target's CLAUDE.md
    _inject_principles_into_claude_md(target, studio_dir)

    # Install (or refresh) the SessionStart update-check hook. A present opt-out
    # sentinel is a durable "leave me alone": it disables the hook and removes any
    # entry a prior install left behind.
    hook_enabled = install_hook and not (dot_studio / UPDATE_CHECK_SENTINEL).exists()
    _install_sessionstart_hook(target, enabled=hook_enabled)

    return dot_studio


def check_studio(target: Path, studio_dir: Optional[Path] = None, fetch: bool = True) -> dict:
    """Check if an installed Studio is up to date with the source.

    ``fetch`` controls whether the staleness check does a short network fetch of
    the source's remote before comparing (default True; ``--no-fetch`` on the CLI
    passes False to compare against cached refs only).

    Returns dict with:
        installed: bool: whether .studio/VERSION exists
        up_to_date: bool: whether all files match source checksums AND the source
            itself is not behind its own remote
        changed: list[str]: files where upstream differs from what was installed (update available)
        missing: list[str]: files in source but not installed
        extra: list[str]: files installed but not in source
        retired: list[str]: the subset of ``extra`` that `update` will DELETE —
            installed .claude/ commands and workflows Studio no longer ships (see
            ``_retired_claude_files``). Counts against ``up_to_date``, because an
            orphaned command left behind is a real difference from the source, and
            without it `update` would short-circuit and never clear it
        locally_modified: list[str]: installed files whose ON-DISK content has
            drifted from the checksum recorded at install, i.e. local edits that an
            `update` would OVERWRITE (the clobber set; spans both .studio/source/
            files and the verbatim .claude/ commands/workflows)
        claude_md_stale: bool: whether the CLAUDE.md coding-principles block is
            behind the current template (not a manifest file, so checked directly)
        source_note: str | None: set when the source was read from the default
            branch instead of the checkout's parked branch, naming what was bypassed
        warning: str | None: set when the live source could not be resolved
            (e.g. run from a stale snapshot), so the result may be unreliable
        staleness: dict | None: whether the resolved source is itself behind its
            git remote, as a plain dict (``SourceStaleness`` fields via
            ``dataclasses.asdict``, so the whole return stays JSON-serializable).
            None when not computed, e.g. an explicit studio_dir was passed so
            staleness detection is disabled.
    """
    target = Path(target).resolve()
    dot_studio = target / ".studio"
    version_path = dot_studio / "VERSION"
    manifest_path = dot_studio / "MANIFEST.json"

    if not version_path.exists():
        return {"installed": False, "up_to_date": False, "changed": [], "missing": [], "extra": [], "retired": [], "locally_modified": [], "claude_md_stale": False, "source_note": None, "warning": None, "staleness": None}

    # When the source was auto-resolved (not handed in explicitly by a test or a
    # caller that already knows) and resolved cleanly, read it from the default
    # branch's committed tree, not whatever branch the checkout is parked on.
    auto_resolved = studio_dir is None
    studio_dir, warning = _resolve_source_dir(target, studio_dir)
    enabled = auto_resolved and warning is None

    # Second question, separate from the file diff: is the resolved source itself
    # behind its own remote? If so, the files could match a source that is itself
    # out of date — a false "up to date". Compute this BEFORE materializing the
    # tree, and when stale, materialize/diff against origin so the change list the
    # user sees is the honest "what origin/main has that you don't".
    staleness = _source_staleness(studio_dir, fetch=fetch) if enabled else None
    override_ref = staleness.remote_ref if (staleness and staleness.is_stale) else None

    # Load installed manifest
    installed_manifest: Dict[str, str] = {}
    if manifest_path.exists():
        try:
            installed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            installed_manifest = {}

    with _source_at_default_branch(studio_dir, enabled, override_ref) as (source_dir, source_note):
        # Build current source manifest (source files + verbatim .claude/ files)
        source_files = _collect_source_files(source_dir)
        manifest_keys = [str(p) for p in source_files] + _claude_manifest_keys(source_dir)
        source_manifest = _build_manifest(manifest_keys, source_dir)

        changed: List[str] = []
        missing: List[str] = []
        extra: List[str] = []

        # Check source files against installed
        for rel, sha in source_manifest.items():
            if rel not in installed_manifest:
                missing.append(rel)
            elif installed_manifest[rel] != sha:
                changed.append(rel)

        # Check for extra installed files
        for rel in installed_manifest:
            if rel not in source_manifest:
                extra.append(rel)

        # Local modifications: installed file on disk differs from what was recorded
        # at install. These are the files an `update` re-install would clobber:
        # source files under .studio/source/ AND the verbatim .claude/ commands/workflows.
        locally_modified: List[str] = []
        for rel, recorded_sha in installed_manifest.items():
            f = _manifest_installed_path(target, rel)
            if f.is_file() and _sha256(f) != recorded_sha:
                locally_modified.append(rel)
        locally_modified.sort()

        # The coding-principles block injected into the target's CLAUDE.md isn't a
        # manifest file, so checksum diffing never sees it drift. Check it directly
        # so a new/changed principle upstream registers as an available update.
        claude_md_stale = _principles_block_stale(target, source_dir)

    retired = _retired_claude_files(extra)
    orphaned = _historical_orphans(target, installed_manifest)

    # `orphaned` counts here on purpose. The whole complaint in #95 is that a repo
    # carrying a stale command reported itself up to date, so a user could invoke
    # pre-rename behavior with nothing saying it was stale. Reporting it without
    # breaking up_to_date would keep exactly that silence.
    up_to_date = (
        not changed
        and not missing
        and not retired
        and not orphaned
        and not claude_md_stale
        and not (staleness and staleness.is_stale)
    )

    return {
        "installed": True,
        "up_to_date": up_to_date,
        "changed": changed,
        "missing": missing,
        "extra": extra,
        "retired": retired,
        "orphaned": orphaned,
        "locally_modified": locally_modified,
        "claude_md_stale": claude_md_stale,
        "source_note": source_note,
        "warning": warning,
        "staleness": asdict(staleness) if staleness else None,
    }


def update_studio(
    target: Path, studio_dir: Optional[Path] = None, force: bool = False, fetch: bool = True,
    install_hook: bool = True, pull_source: bool = False,
) -> dict:
    """Update an installed Studio from the source.

    Preserves user customizations in .studio/ (roles/, scopes.toml, etc.)
    by only overwriting source/ and slash commands.

    Also DELETES the installed ``.claude/`` commands and workflows Studio no longer
    ships, so a renamed command doesn't linger beside its replacement (see
    ``_retired_claude_files``). Only files the manifest records — ones a past
    install wrote — are ever deleted; a hand-written command is left alone.

    PRECONDITION: if any installed source file has local edits (drifted from its
    recorded checksum), the update is BLOCKED, because re-installing would overwrite them.
    Returns ``{"blocked": True, "locally_modified": [...]}`` instead of updating.
    Pass ``force=True`` to overwrite anyway. An edited file that is ALSO retired is
    covered by the same guard: it blocks first, and ``force`` then deletes it.

    ``fetch`` controls whether the staleness check does a short network fetch of
    the source's remote before comparing (default True; ``--no-fetch`` on the CLI
    passes False to compare against cached refs only).

    When the resolved source's own local main is behind its origin, the update
    reads and re-installs from ``origin/main`` instead of the stale local tree,
    and refuses to no-op: a false "already up to date" over a stale source can't
    happen. The source repo itself is never mutated — the returned ``staleness``
    lets the handler print the one ``git -C <source> pull`` command that catches
    the user's checkout up.

    Returns dict with counts of updated/added/removed files, plus a ``warning``
    key (str | None) when the live source could not be resolved (e.g. run from a
    stale snapshot; see ``_resolve_source_dir``) and a ``staleness`` key
    (SourceStaleness | None) describing whether the source was behind its remote.
    """
    target = Path(target).resolve()
    dot_studio = target / ".studio"

    if not (dot_studio / "VERSION").exists():
        raise FileNotFoundError(
            f"Studio not installed at {target}. Run 'init' first."
        )

    # Install/refresh (or, when disabled, remove) the SessionStart update-check hook
    # up front, so it's handled on EVERY path — including the up-to-date and blocked
    # short-circuits below, which return before the re-install. Otherwise
    # `update --no-hook` on an already-current repo (the most common way someone
    # turns the nudge off) would silently no-op and leave the hook in place. The
    # re-install below is handed this same intent, so it lands on the same answer
    # and doing it twice changes nothing. The hook lives in
    # .claude/settings.local.json, separate from the snapshot, so it's correct to
    # handle even when a re-install is blocked on local edits.
    hook_enabled = install_hook and not (dot_studio / UPDATE_CHECK_SENTINEL).exists()
    _install_sessionstart_hook(target, enabled=hook_enabled)

    # Resolve the live source up front so both the check and the re-install copy
    # from upstream, not from the (possibly stale) installed snapshot (#20).
    auto_resolved = studio_dir is None
    source_dir, warning = _resolve_source_dir(target, studio_dir)
    enabled = auto_resolved and warning is None

    # A source we could not resolve is not a source we can update FROM. When
    # _resolve_source_dir gives up it hands back the installed snapshot, and the
    # snapshot has no .claude/ directory in it — the commands and workflows live at
    # the source repo's root, above studio/. So every installed command looks like
    # something Studio has stopped shipping: the re-install below would rebuild
    # MANIFEST.json without them and the prune would then delete all of them off
    # disk (#113). Stop before either can happen and let the caller print the
    # warning. Refusing to update is always recoverable; deleting someone's
    # commands is not.
    if warning is not None:
        return {
            "skipped_no_source": True,
            "updated": 0,
            "added": 0,
            "removed": 0,
            "retired": [],
            "locally_modified": [],
            "claude_md_refreshed": False,
            "source_note": None,
            "warning": warning,
            "staleness": None,
            "source_pull": None,
        }

    # Is the resolved source itself behind its own remote? Compute this HERE, in
    # update's own scope — NOT via the delegated check_studio below, which is
    # called with an explicit dir, so staleness detection is off inside it. When
    # the source is stale, materialize and re-install from origin/main (the fresh
    # tree), and fold is_stale into the no-op short-circuit so a stale source
    # PROCEEDS to reinstall instead of falsely reporting "already up to date".
    staleness = _source_staleness(source_dir, fetch=fetch) if enabled else None

    # Opt-in: fast-forward the user's OWN source checkout when it is cleanly behind
    # origin, so consumers stop getting the recurring "go pull it yourself" nag.
    do_pull = enabled and (pull_source or _source_auto_pull_enabled(source_dir))
    source_pull = None
    if do_pull and staleness and staleness.is_stale:
        source_pull = _fast_forward_source(source_dir, staleness)
        if source_pull.pulled:
            # Source is now current: clear staleness so override_ref becomes None,
            # the install reads the caught-up LOCAL tree (not origin/main), and the
            # manual-pull nag is suppressed. The pull is reported via source_pull.
            staleness = None

    override_ref = staleness.remote_ref if (staleness and staleness.is_stale) else None

    # Read (and copy) from the default branch's committed tree, not whatever
    # branch the source checkout is parked on. One materialization covers both
    # the check and the re-install so they agree on the source.
    with _source_at_default_branch(source_dir, enabled, override_ref) as (effective_dir, source_note):
        # Check what needs updating (explicit dir, so check_studio won't re-materialize).
        status = check_studio(target, effective_dir)

        if status["up_to_date"] and not (staleness and staleness.is_stale):
            return {"updated": 0, "added": 0, "removed": 0, "retired": [], "locally_modified": status["locally_modified"], "claude_md_refreshed": False, "source_note": source_note, "warning": warning, "staleness": asdict(staleness) if staleness else None, "source_pull": asdict(source_pull) if source_pull else None}

        # Preview precondition: refuse to clobber locally-edited snapshot files unless forced.
        locally_modified = status.get("locally_modified", [])
        if locally_modified and not force:
            return {"blocked": True, "locally_modified": locally_modified,
                    "updated": 0, "added": 0, "removed": 0, "retired": [], "claude_md_refreshed": False, "source_note": source_note, "warning": warning, "staleness": asdict(staleness) if staleness else None, "source_pull": asdict(source_pull) if source_pull else None}

        # Re-install (install_studio is idempotent and preserves user dirs). This
        # also re-injects the coding-principles block into CLAUDE.md, refreshing it
        # in place between the sentinel markers and leaving the rest of the file be.
        # Copy from the materialized tree, but record the durable upstream in
        # VERSION — not the throwaway worktree path, which is gone after this.
        override = source_dir if effective_dir != source_dir else None
        # Pass the caller's real hook intent through. install_studio always acts on
        # this flag — it never reads it as "leave the hook alone" — so hard-coding
        # False here told it to DELETE the hook update_studio had just written
        # (#120). Handing it the same intent makes the second pass idempotent.
        install_studio(target, effective_dir, source_path_override=override, install_hook=install_hook)

        # Delete the commands and workflows Studio has stopped shipping. Only files
        # the manifest records — ones this installer wrote — so a command the project
        # author added by hand is never touched. Done after the re-install because
        # install_studio rebuilds the manifest from the current source, which is what
        # drops these keys from it; the files themselves it leaves behind.
        retired = status.get("retired", [])
        for key in retired:
            _manifest_installed_path(target, key).unlink(missing_ok=True)

        return {
            "updated": len(status["changed"]),
            "added": len(status["missing"]),
            "removed": len(retired),
            "retired": retired,
            # Reported, never removed: update cannot reach these (issue #95). Carried out
            # so the CLI can say why the repo still reports as needing an update after a
            # successful one — otherwise it is a nag loop with no stated cause.
            "orphaned": status.get("orphaned", []),
            "locally_modified": locally_modified,
            "claude_md_refreshed": status.get("claude_md_stale", False),
            "source_note": source_note,
            "warning": warning,
            "staleness": asdict(staleness) if staleness else None,
            "source_pull": asdict(source_pull) if source_pull else None,
        }

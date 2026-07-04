"""
Cross-repo Studio installer.

Copies Studio source, slash commands, workflows, config, and manifest into a
target project so that all slash commands (`/run-phase`, `/run-studio-phase`,
`/studio-implement`, `/smoke`, `/unstale`, `/detest`, `/offload`,
`/studio-update`, `/studio-setup`) work natively, including the pause-and-ask
collaboration protocol and the implementation-loop workflow.

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
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

# Files to copy from studio/ into .studio/source/
SOURCE_FILES = [
    "run_phase.py",
    "run_phase_roles.py",
    "role_overrides.py",
    "persona_overrides.py",
    "decision_points.py",
    "question_mode.py",
    "scopes.py",
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
SLASH_COMMANDS = [
    "run-phase.md",
    "run-studio-phase.md",
    "unstale.md",
    "studio-update.md",
    "detest.md",
    "offload.md",
    "studio-setup.md",
    "studio-implement.md",
    "smoke.md",
]

# Claude Code Workflows to copy to {target}/.claude/workflows/ (verbatim, like commands)
WORKFLOW_FILES = [
    "implementation-loop.js",
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


@contextmanager
def _source_at_default_branch(
    studio_dir: Path, enabled: bool
) -> Iterator[Tuple[Path, Optional[str]]]:
    """Yield ``(source_dir, note)`` to read Studio source from.

    When ``enabled`` and ``studio_dir`` is inside a git working copy with a
    resolvable default branch, materialize that branch's *committed* tree in a
    throwaway detached worktree and yield the matching source dir inside it — so
    ``check``/``update`` always read the finished ``main`` version, never
    whatever branch the source checkout happens to be parked on (or its
    uncommitted edits). This is the backstop that keeps a work-in-progress
    branch from leaking into other projects' update checks.

    Falls back to ``studio_dir`` unchanged (``note`` = None) when disabled, not a
    git repo, the branch can't be resolved, or the checkout is already sitting on
    that branch's commit with a clean tree. ``note`` is a short human line naming
    the branch that was bypassed, for the CLI to surface; None when nothing was
    bypassed.
    """
    if not enabled:
        yield studio_dir, None
        return

    top = _git_out(studio_dir, "rev-parse", "--show-toplevel")
    repo = Path(top) if top else None
    ref = _default_branch_ref(repo) if repo else None
    if repo is None or ref is None:
        yield studio_dir, None
        return

    # Fast path: already on the default branch's commit with a clean tree, so the
    # working tree already IS the finished source. Skip the worktree churn.
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
        if current and current != ref:
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

    return dot_studio


def check_studio(target: Path, studio_dir: Optional[Path] = None) -> dict:
    """Check if an installed Studio is up to date with the source.

    Returns dict with:
        installed: bool: whether .studio/VERSION exists
        up_to_date: bool: whether all files match source checksums
        changed: list[str]: files where upstream differs from what was installed (update available)
        missing: list[str]: files in source but not installed
        extra: list[str]: files installed but not in source
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
    """
    target = Path(target).resolve()
    dot_studio = target / ".studio"
    version_path = dot_studio / "VERSION"
    manifest_path = dot_studio / "MANIFEST.json"

    if not version_path.exists():
        return {"installed": False, "up_to_date": False, "changed": [], "missing": [], "extra": [], "locally_modified": [], "claude_md_stale": False, "source_note": None, "warning": None}

    # When the source was auto-resolved (not handed in explicitly by a test or a
    # caller that already knows) and resolved cleanly, read it from the default
    # branch's committed tree, not whatever branch the checkout is parked on.
    auto_resolved = studio_dir is None
    studio_dir, warning = _resolve_source_dir(target, studio_dir)
    enabled = auto_resolved and warning is None

    # Load installed manifest
    installed_manifest: Dict[str, str] = {}
    if manifest_path.exists():
        try:
            installed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            installed_manifest = {}

    with _source_at_default_branch(studio_dir, enabled) as (source_dir, source_note):
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

    up_to_date = not changed and not missing and not claude_md_stale

    return {
        "installed": True,
        "up_to_date": up_to_date,
        "changed": changed,
        "missing": missing,
        "extra": extra,
        "locally_modified": locally_modified,
        "claude_md_stale": claude_md_stale,
        "source_note": source_note,
        "warning": warning,
    }


def update_studio(target: Path, studio_dir: Optional[Path] = None, force: bool = False) -> dict:
    """Update an installed Studio from the source.

    Preserves user customizations in .studio/ (roles/, scopes.toml, etc.)
    by only overwriting source/ and slash commands.

    PRECONDITION: if any installed source file has local edits (drifted from its
    recorded checksum), the update is BLOCKED, because re-installing would overwrite them.
    Returns ``{"blocked": True, "locally_modified": [...]}`` instead of updating.
    Pass ``force=True`` to overwrite anyway.

    Returns dict with counts of updated/added/removed files, plus a ``warning``
    key (str | None) when the live source could not be resolved (e.g. run from a
    stale snapshot; see ``_resolve_source_dir``).
    """
    target = Path(target).resolve()
    dot_studio = target / ".studio"

    if not (dot_studio / "VERSION").exists():
        raise FileNotFoundError(
            f"Studio not installed at {target}. Run 'init' first."
        )

    # Resolve the live source up front so both the check and the re-install copy
    # from upstream, not from the (possibly stale) installed snapshot (#20).
    auto_resolved = studio_dir is None
    source_dir, warning = _resolve_source_dir(target, studio_dir)
    enabled = auto_resolved and warning is None

    # Read (and copy) from the default branch's committed tree, not whatever
    # branch the source checkout is parked on. One materialization covers both
    # the check and the re-install so they agree on the source.
    with _source_at_default_branch(source_dir, enabled) as (effective_dir, source_note):
        # Check what needs updating (explicit dir, so check_studio won't re-materialize).
        status = check_studio(target, effective_dir)

        if status["up_to_date"]:
            return {"updated": 0, "added": 0, "removed": 0, "locally_modified": status["locally_modified"], "claude_md_refreshed": False, "source_note": source_note, "warning": warning}

        # Preview precondition: refuse to clobber locally-edited snapshot files unless forced.
        locally_modified = status.get("locally_modified", [])
        if locally_modified and not force:
            return {"blocked": True, "locally_modified": locally_modified,
                    "updated": 0, "added": 0, "removed": 0, "claude_md_refreshed": False, "source_note": source_note, "warning": warning}

        # Re-install (install_studio is idempotent and preserves user dirs). This
        # also re-injects the coding-principles block into CLAUDE.md, refreshing it
        # in place between the sentinel markers and leaving the rest of the file be.
        # Copy from the materialized tree, but record the durable upstream in
        # VERSION — not the throwaway worktree path, which is gone after this.
        override = source_dir if effective_dir != source_dir else None
        install_studio(target, effective_dir, source_path_override=override)

        return {
            "updated": len(status["changed"]),
            "added": len(status["missing"]),
            "removed": 0,  # We don't remove extra files
            "locally_modified": locally_modified,
            "claude_md_refreshed": status.get("claude_md_stale", False),
            "source_note": source_note,
            "warning": warning,
        }

"""
Cross-repo Studio installer.

Copies Studio source, slash commands, config, and manifest into a target
project so that all slash commands (`/run-phase`, `/run-studio-phase`,
`/unstale`, `/detest`, `/offload`, `/studio-update`, `/studio-setup`) work natively —
including the pause-and-ask collaboration protocol.

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
]

# Claude Code Workflows to copy to {target}/.claude/workflows/ (verbatim, like commands)
WORKFLOW_FILES = [
    "implementation-loop.js",
]

# Sentinels for CLAUDE.md injection — update replaces content between these markers
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
    snapshot — so comparing it against the installed ``MANIFEST.json`` compares
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
        # where the live source is) — trust it.
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



def _build_manifest(
    source_files: List[Path],
    studio_dir: Path,
) -> Dict[str, str]:
    """Build install manifest: {relative_path: sha256}."""
    manifest: Dict[str, str] = {}
    for rel in source_files:
        full = studio_dir / rel
        if full.is_file():
            manifest[str(rel)] = _sha256(full)
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


def install_studio(target: Path, studio_dir: Optional[Path] = None) -> Path:
    """Install Studio into a target project directory.

    Creates:
        {target}/.studio/source/     — Studio Python source + config
        {target}/.claude/commands/    — Slash commands (verbatim, use .studio/source/ paths)
        {target}/.claude/workflows/   — Claude Code workflows (verbatim, resolve .studio/source/ at run time)
        {target}/.studio/VERSION      — Version info
        {target}/.studio/MANIFEST.json — Install manifest with checksums

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

    # Build and write manifest
    manifest = _build_manifest(source_files, studio_dir)
    manifest_path = dot_studio / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    # Write VERSION
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    git = _git_info(studio_dir.parent)
    version_info = {
        "installed_at": now,
        "source_path": str(studio_dir),
        "commit": git.get("commit", "unknown"),
        "commit_date": git.get("commit_date", ""),
        "file_count": len(manifest),
    }
    version_path = dot_studio / "VERSION"
    version_path.write_text(
        json.dumps(version_info, indent=2), encoding="utf-8"
    )

    # Inject coding principles into target's CLAUDE.md
    _inject_principles_into_claude_md(target, studio_dir)

    return dot_studio


def check_studio(target: Path, studio_dir: Optional[Path] = None) -> dict:
    """Check if an installed Studio is up to date with the source.

    Returns dict with:
        installed: bool — whether .studio/VERSION exists
        up_to_date: bool — whether all files match source checksums
        changed: list[str] — files that differ
        missing: list[str] — files in source but not installed
        extra: list[str] — files installed but not in source
        warning: str | None — set when the live source could not be resolved
            (e.g. run from a stale snapshot), so the result may be unreliable
    """
    target = Path(target).resolve()
    dot_studio = target / ".studio"
    version_path = dot_studio / "VERSION"
    manifest_path = dot_studio / "MANIFEST.json"

    if not version_path.exists():
        return {"installed": False, "up_to_date": False, "changed": [], "missing": [], "extra": [], "warning": None}

    studio_dir, warning = _resolve_source_dir(target, studio_dir)

    # Load installed manifest
    installed_manifest: Dict[str, str] = {}
    if manifest_path.exists():
        try:
            installed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            installed_manifest = {}

    # Build current source manifest
    source_files = _collect_source_files(studio_dir)
    source_manifest = _build_manifest(source_files, studio_dir)

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

    up_to_date = not changed and not missing

    return {
        "installed": True,
        "up_to_date": up_to_date,
        "changed": changed,
        "missing": missing,
        "extra": extra,
        "warning": warning,
    }


def update_studio(target: Path, studio_dir: Optional[Path] = None) -> dict:
    """Update an installed Studio from the source.

    Preserves user customizations in .studio/ (roles/, scopes.toml, etc.)
    by only overwriting source/ and slash commands.

    Returns dict with counts of updated/added/removed files, plus a ``warning``
    key (str | None) when the live source could not be resolved (e.g. run from a
    stale snapshot — see ``_resolve_source_dir``).
    """
    target = Path(target).resolve()
    dot_studio = target / ".studio"

    if not (dot_studio / "VERSION").exists():
        raise FileNotFoundError(
            f"Studio not installed at {target}. Run 'init' first."
        )

    # Resolve the live source up front so both the check and the re-install copy
    # from upstream — not from the (possibly stale) installed snapshot (#20).
    source_dir, warning = _resolve_source_dir(target, studio_dir)

    # Check what needs updating
    status = check_studio(target, source_dir)

    if status["up_to_date"]:
        return {"updated": 0, "added": 0, "removed": 0, "warning": warning}

    # Re-install (install_studio is idempotent and preserves user dirs)
    install_studio(target, source_dir)

    return {
        "updated": len(status["changed"]),
        "added": len(status["missing"]),
        "removed": 0,  # We don't remove extra files
        "warning": warning,
    }

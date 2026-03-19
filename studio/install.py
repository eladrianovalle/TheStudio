"""
Cross-repo Studio installer.

Copies Studio source, slash commands, config, and manifest into a target
project so that `/run-phase` and `/run-studio-phase` work natively —
including the pause-and-ask collaboration protocol.

Usage via run_phase.py:
    python run_phase.py init --target /path/to/project
    python run_phase.py check --target /path/to/project
    python run_phase.py update --target /path/to/project
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Files to copy from studio/ into .studio/source/
SOURCE_FILES = [
    "run_phase.py",
    "run_phase_roles.py",
    "role_overrides.py",
    "decision_points.py",
    "question_mode.py",
    "scopes.py",
    "cleanup.py",
    "rerun.py",
    "verdict.py",
    "install.py",
    "studio.manifest.json",
    "validators/__init__.py",
    "validators/document_validator.py",
    "validators/code_validator.py",
    "config/scopes.toml",
    "config/studio_settings.toml",
    "docs/STUDIO_BRIDGE_TEMPLATE.md",
]

# Glob patterns for additional files
ROLE_PACK_GLOB = "role_packs/*.json"
PROMPT_DOC_GLOB = "docs/role_prompts/*.md"

# Slash commands to copy to {target}/.claude/commands/
SLASH_COMMANDS = [
    "run-phase.md",
    "run-studio-phase.md",
]

# Marker to replace in slash commands
_STUDIO_ROOT_MARKER = '"$STUDIO_ROOT/'
_STUDIO_ROOT_REPLACEMENT_PREFIX = '"'  # filled in at install time


def _get_studio_root() -> Path:
    """Get the root of the Studio source repo (parent of studio/)."""
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


def _rewrite_slash_command(content: str, studio_root_path: str) -> str:
    """Rewrite $STUDIO_ROOT references in slash commands to point to installed source.

    Handles patterns like:
        python "$STUDIO_ROOT/run_phase.py" ...
        Read it at `studio/{prompt_doc}` ...
    """
    # Replace $STUDIO_ROOT with the installed path
    content = content.replace("$STUDIO_ROOT/", f"{studio_root_path}/")
    content = content.replace("$STUDIO_ROOT", studio_root_path)

    # Replace bare `studio/` references to prompt docs
    content = content.replace(
        "read it at `studio/",
        f"read it at `{studio_root_path}/",
    )

    return content


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


def install_studio(target: Path, studio_dir: Optional[Path] = None) -> Path:
    """Install Studio into a target project directory.

    Creates:
        {target}/.studio/source/     — Studio Python source + config
        {target}/.claude/commands/    — Slash commands (rewritten)
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

    # Copy source files
    for rel in source_files:
        src = studio_dir / rel
        dst = source_dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # Copy and rewrite slash commands
    commands_dest.mkdir(parents=True, exist_ok=True)
    # Relative path from target root to .studio/source
    installed_root = ".studio/source"

    commands_src = studio_dir.parent / ".claude" / "commands"
    for cmd_name in SLASH_COMMANDS:
        src = commands_src / cmd_name
        if not src.exists():
            continue
        content = src.read_text(encoding="utf-8")
        content = _rewrite_slash_command(content, installed_root)
        (commands_dest / cmd_name).write_text(content, encoding="utf-8")

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

    return dot_studio


def check_studio(target: Path, studio_dir: Optional[Path] = None) -> dict:
    """Check if an installed Studio is up to date with the source.

    Returns dict with:
        installed: bool — whether .studio/VERSION exists
        up_to_date: bool — whether all files match source checksums
        changed: list[str] — files that differ
        missing: list[str] — files in source but not installed
        extra: list[str] — files installed but not in source
    """
    if studio_dir is None:
        studio_dir = _get_studio_root()

    target = Path(target).resolve()
    dot_studio = target / ".studio"
    version_path = dot_studio / "VERSION"
    manifest_path = dot_studio / "MANIFEST.json"

    if not version_path.exists():
        return {"installed": False, "up_to_date": False, "changed": [], "missing": [], "extra": []}

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
    }


def update_studio(target: Path, studio_dir: Optional[Path] = None) -> dict:
    """Update an installed Studio from the source.

    Preserves user customizations in .studio/ (roles/, scopes.toml, etc.)
    by only overwriting source/ and slash commands.

    Returns dict with counts of updated/added/removed files.
    """
    if studio_dir is None:
        studio_dir = _get_studio_root()

    target = Path(target).resolve()
    dot_studio = target / ".studio"

    if not (dot_studio / "VERSION").exists():
        raise FileNotFoundError(
            f"Studio not installed at {target}. Run 'init' first."
        )

    # Check what needs updating
    status = check_studio(target, studio_dir)

    if status["up_to_date"]:
        return {"updated": 0, "added": 0, "removed": 0}

    # Re-install (install_studio is idempotent and preserves user dirs)
    install_studio(target, studio_dir)

    return {
        "updated": len(status["changed"]),
        "added": len(status["missing"]),
        "removed": 0,  # We don't remove extra files
    }

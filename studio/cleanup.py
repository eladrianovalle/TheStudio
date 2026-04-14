from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redefine]

CONFIG_RELATIVE_PATH = Path("config") / "studio_settings.toml"
DEFAULT_TTL_DAYS = 30
DEFAULT_SIZE_LIMIT_MB = 900


@dataclass(frozen=True)
class CleanupSettings:
    ttl_days: int = DEFAULT_TTL_DAYS
    size_limit_mb: int = DEFAULT_SIZE_LIMIT_MB

    @property
    def ttl_delta(self) -> timedelta:
        days = max(0, self.ttl_days)
        return timedelta(days=days)

    @property
    def size_limit_bytes(self) -> int:
        return max(0, self.size_limit_mb) * 1024 * 1024


@dataclass(frozen=True)
class RunRecord:
    phase: str
    run_id: str
    path: Path
    created_at: datetime
    size_bytes: int

    @property
    def identifier(self) -> str:
        return f"{self.phase}/{self.run_id}"


@dataclass(frozen=True)
class DeletionRecord:
    run: RunRecord
    reason: str  # "ttl" or "budget"


@dataclass
class CleanupReport:
    settings: CleanupSettings
    total_runs: int
    total_size_bytes: int
    deletions: List[DeletionRecord]
    dry_run: bool
    errors: List[str]

    @property
    def freed_bytes(self) -> int:
        return sum(record.run.size_bytes for record in self.deletions)

    def reasons_summary(self) -> Dict[str, int]:
        summary: Dict[str, int] = {}
        for record in self.deletions:
            summary[record.reason] = summary.get(record.reason, 0) + 1
        return summary


class CleanupError(RuntimeError):
    """Raised when cleanup configuration cannot be parsed."""


def load_cleanup_settings(studio_root: Path) -> CleanupSettings:
    path = studio_root / CONFIG_RELATIVE_PATH
    if not path.exists():
        return CleanupSettings()
    try:
        with open(path, "rb") as f:
            parsed = tomllib.load(f)
    except OSError as exc:
        raise CleanupError(f"Failed to read cleanup config at {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise CleanupError(f"Invalid TOML in cleanup config at {path}: {exc}") from exc

    cleanup_section = parsed.get("cleanup", {})

    ttl_days = _safe_int(cleanup_section.get("ttl_days"), DEFAULT_TTL_DAYS)
    size_limit_mb = _safe_int(
        cleanup_section.get("size_limit_mb"), DEFAULT_SIZE_LIMIT_MB
    )
    if size_limit_mb >= 1024:
        size_limit_mb = 1023
    return CleanupSettings(ttl_days=ttl_days, size_limit_mb=size_limit_mb)


def cleanup_runs(
    output_root: Path,
    settings: CleanupSettings,
    *,
    now: Optional[datetime] = None,
    dry_run: bool = False,
) -> CleanupReport:
    current_time = now or datetime.now(timezone.utc)
    report = CleanupReport(
        settings=settings,
        total_runs=0,
        total_size_bytes=0,
        deletions=[],
        dry_run=dry_run,
        errors=[],
    )

    # Clean up loose files (legacy artifacts not inside run_* directories)
    loose_deleted = _cleanup_loose_files(output_root, settings, now=current_time, dry_run=dry_run)
    report.errors.extend(loose_deleted)

    run_records = _collect_runs(output_root)
    if not run_records:
        return report

    report.total_runs = len(run_records)
    report.total_size_bytes = sum(record.size_bytes for record in run_records)

    to_delete: List[DeletionRecord] = []
    cutoff = current_time - settings.ttl_delta

    if settings.ttl_days > 0:
        for record in run_records:
            if record.created_at < cutoff:
                to_delete.append(DeletionRecord(run=record, reason="ttl"))

    remaining = [record for record in run_records if record not in {d.run for d in to_delete}]
    remaining_size = sum(record.size_bytes for record in remaining)

    size_limit = settings.size_limit_bytes
    if size_limit and remaining_size > size_limit:
        sorted_remaining = sorted(remaining, key=lambda rec: rec.created_at)
        for record in sorted_remaining:
            if remaining_size <= size_limit:
                break
            to_delete.append(DeletionRecord(run=record, reason="budget"))
            remaining_size -= record.size_bytes

    seen_paths = set()
    final_deletions: List[DeletionRecord] = []
    for record in to_delete:
        if record.run.path in seen_paths:
            continue
        seen_paths.add(record.run.path)
        final_deletions.append(record)
        try:
            if not dry_run and record.run.path.exists():
                shutil.rmtree(record.run.path)
        except OSError as exc:
            report.errors.append(
                f"Failed to delete {record.run.path}: {exc}"
            )

    report.deletions = final_deletions
    return report


def format_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TB"


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


_PRESERVED_FILENAMES = frozenset({"index.md"})


def _cleanup_loose_files(
    output_root: Path,
    settings: CleanupSettings,
    *,
    now: Optional[datetime] = None,
    dry_run: bool = False,
) -> List[str]:
    """Remove loose files older than TTL from output root and phase directories.

    Loose files are artifacts not inside ``run_*`` directories — typically
    legacy outputs from before the structured run directory format.
    Preserves ``index.md`` (actively regenerated by finalize).

    Returns a list of error messages (empty on success).
    """
    if not output_root.exists() or settings.ttl_days <= 0:
        return []

    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - settings.ttl_delta
    errors: List[str] = []

    # Collect loose files from output root + phase subdirectories
    candidates: List[Path] = []
    for entry in output_root.iterdir():
        if entry.is_file() and entry.name not in _PRESERVED_FILENAMES:
            candidates.append(entry)
        elif entry.is_dir():
            for child in entry.iterdir():
                if child.is_file() and child.name not in _PRESERVED_FILENAMES:
                    candidates.append(child)

    for path in candidates:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        except OSError:
            continue
        if mtime < cutoff:
            try:
                if not dry_run:
                    path.unlink()
            except OSError as exc:
                errors.append(f"Failed to delete loose file {path}: {exc}")

    return errors


def _collect_runs(output_root: Path) -> List[RunRecord]:
    records: List[RunRecord] = []
    if not output_root.exists():
        return records

    for phase_dir in sorted(output_root.iterdir()):
        if not phase_dir.is_dir():
            continue
        for run_dir in sorted(phase_dir.glob("run_*")):
            if not run_dir.is_dir():
                continue
            record = _build_run_record(phase_dir.name, run_dir)
            if record:
                records.append(record)
    return records


def _build_run_record(phase: str, run_dir: Path) -> Optional[RunRecord]:
    run_id = run_dir.name
    meta_path = run_dir / "run.json"
    created_at = None
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            created_iso = meta.get("created_iso")
            if created_iso:
                created_at = datetime.fromisoformat(created_iso)
        except Exception:
            created_at = None
    if created_at is None:
        created_at = datetime.fromtimestamp(run_dir.stat().st_mtime, timezone.utc)

    size_bytes = _directory_size(run_dir)
    return RunRecord(
        phase=phase,
        run_id=run_id,
        path=run_dir,
        created_at=created_at,
        size_bytes=size_bytes,
    )


def _directory_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


__all__ = [
    "CleanupSettings",
    "CleanupReport",
    "CleanupError",
    "cleanup_runs",
    "format_bytes",
    "load_cleanup_settings",
]

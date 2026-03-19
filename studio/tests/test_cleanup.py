#!/usr/bin/env python3
"""Tests for TTL and budget-based cleanup of run artifacts."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cleanup import (
    CleanupSettings,
    cleanup_runs,
    format_bytes,
    load_cleanup_settings,
    _cleanup_loose_files,
    DEFAULT_TTL_DAYS,
    DEFAULT_SIZE_LIMIT_MB,
)


def _write_run(
    output_root: Path,
    phase: str,
    run_id: str,
    created_iso: str,
    size_bytes: int,
    *,
    run_json_content: str | None = None,
) -> Path:
    """Create a fake run directory with run.json and an artifact of *size_bytes*."""
    run_dir = output_root / phase / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if run_json_content is not None:
        (run_dir / "run.json").write_text(run_json_content, encoding="utf-8")
    else:
        (run_dir / "run.json").write_text(
            f'{{"run_id":"{run_id}","phase":"{phase}","created_iso":"{created_iso}"}}',
            encoding="utf-8",
        )
    (run_dir / "artifact.bin").write_bytes(b"x" * size_bytes)
    return run_dir


# ── existing tests ────────────────────────────────────────────────────


def test_load_cleanup_settings_defaults_when_missing(tmp_path):
    settings = load_cleanup_settings(tmp_path)
    assert settings.ttl_days == DEFAULT_TTL_DAYS
    assert settings.size_limit_mb == DEFAULT_SIZE_LIMIT_MB


def test_cleanup_runs_enforces_ttl_and_size_budget(tmp_path):
    output_root = tmp_path / "output"
    now = datetime(2025, 1, 15, tzinfo=timezone.utc)
    old_iso = (now - timedelta(days=10)).isoformat()
    recent_iso = (now - timedelta(days=1)).isoformat()

    old_run = _write_run(output_root, "market", "run_market_old", old_iso, size_bytes=50_000)
    mid_run = _write_run(output_root, "market", "run_market_mid", recent_iso, size_bytes=700_000)
    newest_run = _write_run(output_root, "market", "run_market_new", recent_iso, size_bytes=600_000)

    settings = CleanupSettings(ttl_days=7, size_limit_mb=1)
    report = cleanup_runs(output_root, settings, now=now, dry_run=False)

    removed_ids = {record.run.run_id: record.reason for record in report.deletions}
    assert removed_ids["run_market_old"] == "ttl"
    assert removed_ids["run_market_mid"] == "budget"
    assert "run_market_new" not in removed_ids

    assert not old_run.exists()
    assert not mid_run.exists()
    assert newest_run.exists()


def test_cleanup_runs_dry_run_does_not_delete(tmp_path):
    output_root = tmp_path / "output"
    iso = datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat()
    run_dir = _write_run(output_root, "design", "run_design_old", iso, size_bytes=100_000)
    settings = CleanupSettings(ttl_days=1, size_limit_mb=1)

    report = cleanup_runs(output_root, settings, now=datetime(2025, 1, 10, tzinfo=timezone.utc), dry_run=True)

    assert report.deletions
    assert run_dir.exists()


# ── TTL boundary tests ────────────────────────────────────────────────


def test_ttl_boundary_exact_30_days_kept(tmp_path):
    """A run created exactly 30 days ago should NOT be deleted (cutoff is strict <)."""
    output_root = tmp_path / "output"
    now = datetime(2025, 2, 1, tzinfo=timezone.utc)
    boundary_iso = (now - timedelta(days=30)).isoformat()
    run_dir = _write_run(output_root, "market", "run_market_boundary", boundary_iso, size_bytes=1_000)

    settings = CleanupSettings(ttl_days=30, size_limit_mb=900)
    report = cleanup_runs(output_root, settings, now=now, dry_run=False)

    removed_ids = {record.run.run_id for record in report.deletions}
    assert "run_market_boundary" not in removed_ids
    assert run_dir.exists()


def test_ttl_boundary_31_days_deleted(tmp_path):
    """A run created 31 days ago should be deleted by TTL."""
    output_root = tmp_path / "output"
    now = datetime(2025, 2, 1, tzinfo=timezone.utc)
    old_iso = (now - timedelta(days=31)).isoformat()
    run_dir = _write_run(output_root, "market", "run_market_expired", old_iso, size_bytes=1_000)

    settings = CleanupSettings(ttl_days=30, size_limit_mb=900)
    report = cleanup_runs(output_root, settings, now=now, dry_run=False)

    removed_ids = {record.run.run_id: record.reason for record in report.deletions}
    assert removed_ids.get("run_market_expired") == "ttl"
    assert not run_dir.exists()


# ── Budget-only test ──────────────────────────────────────────────────


def test_budget_only_deletes_oldest_first(tmp_path):
    """Runs within TTL but exceeding budget: oldest runs deleted first."""
    output_root = tmp_path / "output"
    now = datetime(2025, 2, 1, tzinfo=timezone.utc)

    oldest_iso = (now - timedelta(days=5)).isoformat()
    middle_iso = (now - timedelta(days=3)).isoformat()
    newest_iso = (now - timedelta(days=1)).isoformat()

    oldest_run = _write_run(output_root, "tech", "run_tech_oldest", oldest_iso, size_bytes=400_000)
    _write_run(output_root, "tech", "run_tech_middle", middle_iso, size_bytes=400_000)
    newest_run = _write_run(output_root, "tech", "run_tech_newest", newest_iso, size_bytes=400_000)

    settings = CleanupSettings(ttl_days=30, size_limit_mb=1)
    report = cleanup_runs(output_root, settings, now=now, dry_run=False)

    removed_ids = {record.run.run_id: record.reason for record in report.deletions}
    assert all(reason == "budget" for reason in removed_ids.values())
    assert "run_tech_oldest" in removed_ids
    assert "run_tech_newest" not in removed_ids
    assert not oldest_run.exists()
    assert newest_run.exists()


# ── TTL-only test ─────────────────────────────────────────────────────


def test_ttl_only_within_budget(tmp_path):
    """Expired runs are deleted even when total size is within budget."""
    output_root = tmp_path / "output"
    now = datetime(2025, 3, 1, tzinfo=timezone.utc)

    expired_iso = (now - timedelta(days=60)).isoformat()
    fresh_iso = (now - timedelta(days=1)).isoformat()

    expired_run = _write_run(output_root, "design", "run_design_old", expired_iso, size_bytes=500)
    fresh_run = _write_run(output_root, "design", "run_design_new", fresh_iso, size_bytes=500)

    settings = CleanupSettings(ttl_days=30, size_limit_mb=900)
    report = cleanup_runs(output_root, settings, now=now, dry_run=False)

    removed_ids = {record.run.run_id: record.reason for record in report.deletions}
    assert removed_ids.get("run_design_old") == "ttl"
    assert "run_design_new" not in removed_ids
    assert not expired_run.exists()
    assert fresh_run.exists()


# ── Corrupt run.json test ─────────────────────────────────────────────


def test_corrupt_run_json_does_not_crash(tmp_path):
    """A run directory with invalid JSON in run.json should not crash cleanup."""
    output_root = tmp_path / "output"
    now = datetime(2025, 2, 1, tzinfo=timezone.utc)

    corrupt_run = _write_run(
        output_root,
        "market",
        "run_market_corrupt",
        "",
        size_bytes=500,
        run_json_content="NOT VALID JSON {{{",
    )

    valid_iso = (now - timedelta(days=1)).isoformat()
    valid_run = _write_run(output_root, "market", "run_market_valid", valid_iso, size_bytes=500)

    settings = CleanupSettings(ttl_days=30, size_limit_mb=900)
    report = cleanup_runs(output_root, settings, now=now, dry_run=False)

    assert report.total_runs == 2
    assert report.errors == []
    assert valid_run.exists()


# ── format_bytes edge cases ──────────────────────────────────────────


# ── Loose file cleanup tests ─────────────────────────────────────────


def _write_loose_file(output_root: Path, *parts: str, age_days: int = 0) -> Path:
    """Create a loose file and backdate its mtime."""
    path = output_root.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("legacy content", encoding="utf-8")
    if age_days > 0:
        import os
        old_time = (datetime.now(timezone.utc) - timedelta(days=age_days)).timestamp()
        os.utime(path, (old_time, old_time))
    return path


def test_loose_files_deleted_when_older_than_ttl(tmp_path):
    """Loose files older than TTL are removed."""
    output_root = tmp_path / "output"
    old_file = _write_loose_file(output_root, "old_pipeline.json", age_days=45)
    fresh_file = _write_loose_file(output_root, "recent.json", age_days=5)

    settings = CleanupSettings(ttl_days=30, size_limit_mb=900)
    errors = _cleanup_loose_files(output_root, settings)

    assert not old_file.exists()
    assert fresh_file.exists()
    assert errors == []


def test_loose_files_in_phase_dirs_cleaned(tmp_path):
    """Loose files inside phase subdirectories are also cleaned."""
    output_root = tmp_path / "output"
    old_file = _write_loose_file(output_root, "market", "market_20251220.md", age_days=100)
    # A run directory should be untouched by loose file cleanup
    run_dir = output_root / "market" / "run_market_20260101"
    run_dir.mkdir(parents=True)
    (run_dir / "instructions.md").write_text("keep me")

    settings = CleanupSettings(ttl_days=30, size_limit_mb=900)
    _cleanup_loose_files(output_root, settings)

    assert not old_file.exists()
    assert (run_dir / "instructions.md").exists()


def test_index_md_preserved(tmp_path):
    """index.md is preserved even when older than TTL."""
    output_root = tmp_path / "output"
    index = _write_loose_file(output_root, "index.md", age_days=100)

    settings = CleanupSettings(ttl_days=30, size_limit_mb=900)
    _cleanup_loose_files(output_root, settings)

    assert index.exists()


def test_loose_files_dry_run_via_cleanup_runs(tmp_path):
    """Loose files are not deleted in dry_run mode (via cleanup_runs integration)."""
    output_root = tmp_path / "output"
    old_file = _write_loose_file(output_root, "legacy.json", age_days=60)

    settings = CleanupSettings(ttl_days=30, size_limit_mb=900)
    now = datetime.now(timezone.utc)
    cleanup_runs(output_root, settings, now=now, dry_run=True)

    assert old_file.exists()


def test_loose_files_no_dir_no_error(tmp_path):
    """No error when output root doesn't exist."""
    output_root = tmp_path / "nonexistent"
    settings = CleanupSettings(ttl_days=30, size_limit_mb=900)
    errors = _cleanup_loose_files(output_root, settings)
    assert errors == []


def test_loose_files_ttl_zero_skips(tmp_path):
    """TTL of 0 means no TTL enforcement — loose files not cleaned."""
    output_root = tmp_path / "output"
    old_file = _write_loose_file(output_root, "ancient.json", age_days=500)

    settings = CleanupSettings(ttl_days=0, size_limit_mb=900)
    errors = _cleanup_loose_files(output_root, settings)

    assert old_file.exists()
    assert errors == []


# ── format_bytes edge cases ──────────────────────────────────────────


@pytest.mark.parametrize(
    "input_bytes, expected",
    [
        (0, "0.0B"),
        (1023, "1023.0B"),
        (1024, "1.0KB"),
        (1024 * 1024, "1.0MB"),
        (1024 * 1024 * 1024, "1.0GB"),
        (1024 * 1024 * 1024 * 1024, "1.0TB"),
        (512, "512.0B"),
        (1536, "1.5KB"),
    ],
    ids=[
        "zero_bytes",
        "just_under_1KB",
        "exactly_1KB",
        "exactly_1MB",
        "exactly_1GB",
        "exactly_1TB",
        "mid_range_bytes",
        "fractional_KB",
    ],
)
def test_format_bytes_edge_cases(input_bytes, expected):
    assert format_bytes(input_bytes) == expected

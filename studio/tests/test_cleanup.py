import importlib.util
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

CLEANUP_PATH = Path(__file__).resolve().parents[1] / "cleanup.py"
_spec = importlib.util.spec_from_file_location("cleanup_module", CLEANUP_PATH)
cleanup = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules[_spec.name] = cleanup
_spec.loader.exec_module(cleanup)


def _write_run(output_root: Path, phase: str, run_id: str, created_iso: str, size_bytes: int) -> Path:
    run_dir = output_root / phase / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        f'{{"run_id":"{run_id}","phase":"{phase}","created_iso":"{created_iso}"}}',
        encoding="utf-8",
    )
    (run_dir / "artifact.bin").write_bytes(b"x" * size_bytes)
    return run_dir


def test_load_cleanup_settings_defaults_when_missing(tmp_path):
    settings = cleanup.load_cleanup_settings(tmp_path)
    assert settings.ttl_days == cleanup.DEFAULT_TTL_DAYS
    assert settings.size_limit_mb == cleanup.DEFAULT_SIZE_LIMIT_MB


def test_cleanup_runs_enforces_ttl_and_size_budget(tmp_path):
    output_root = tmp_path / "output"
    now = datetime(2025, 1, 15, tzinfo=timezone.utc)
    old_iso = (now - timedelta(days=10)).isoformat()
    recent_iso = (now - timedelta(days=1)).isoformat()

    old_run = _write_run(output_root, "market", "run_market_old", old_iso, size_bytes=50_000)
    mid_run = _write_run(output_root, "market", "run_market_mid", recent_iso, size_bytes=700_000)
    newest_run = _write_run(output_root, "market", "run_market_new", recent_iso, size_bytes=600_000)

    settings = cleanup.CleanupSettings(ttl_days=7, size_limit_mb=1)
    report = cleanup.cleanup_runs(output_root, settings, now=now, dry_run=False)

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
    settings = cleanup.CleanupSettings(ttl_days=1, size_limit_mb=1)

    report = cleanup.cleanup_runs(output_root, settings, now=datetime(2025, 1, 10, tzinfo=timezone.utc), dry_run=True)

    assert report.deletions
    assert run_dir.exists()

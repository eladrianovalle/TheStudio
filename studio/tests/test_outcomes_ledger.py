"""Tests for auto-appending a finalized run's outcome record to a local ledger.

The single-user simplification (SESSION_ANALYTICS_PLAN.md Part 3): instead of
running export-outcomes then import-outcomes by hand, a ``[outcomes] ledger_path``
in ``.studio/integrations.toml`` makes finalize append each run's record straight
to that ledger — rated or not, deduped by (repo, run_id), and soft-fail.
"""
import json

import run_phase
from conftest import make_prepare_args, make_finalize_args


def _write_outcomes_config(studio_root, body: str) -> None:
    cfg_dir = studio_root / ".studio"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "integrations.toml").write_text(body, encoding="utf-8")


def _finalizable_run(studio_root, phase="market"):
    """Prepare a run and seed the artifacts finalize requires; return (id, dir)."""
    run_id = run_phase.prepare_run(make_prepare_args(phase=phase))
    run_dir = studio_root / "output" / phase / run_id
    (run_dir / "advocate_1.md").write_text("Advocate", encoding="utf-8")
    (run_dir / "contrarian_1.md").write_text("Contrarian", encoding="utf-8")
    (run_dir / "summary.md").write_text("Summary", encoding="utf-8")
    return run_id, run_dir


# --------------------------------------------------------------------------- #
# Config reader
# --------------------------------------------------------------------------- #
def test_config_reader_returns_path_when_set(studio_root):
    ledger = studio_root / "knowledge" / "outcomes.jsonl"
    _write_outcomes_config(studio_root, f'[outcomes]\nledger_path = "{ledger}"\n')

    result = run_phase.get_configured_ledger_path()

    assert result == ledger.resolve()


def test_config_reader_none_when_config_absent(studio_root):
    assert run_phase.get_configured_ledger_path() is None


def test_config_reader_none_when_table_missing(studio_root):
    # Config exists but only carries an unrelated table.
    _write_outcomes_config(studio_root, '[slack]\nenabled = true\n')
    assert run_phase.get_configured_ledger_path() is None


def test_config_reader_none_when_key_missing(studio_root):
    _write_outcomes_config(studio_root, '[outcomes]\nother = "x"\n')
    assert run_phase.get_configured_ledger_path() is None


def test_config_reader_none_when_malformed(studio_root):
    _write_outcomes_config(studio_root, '[outcomes]\nledger_path = "unterminated\n')
    assert run_phase.get_configured_ledger_path() is None


def test_config_reader_expands_user(studio_root, monkeypatch):
    home = studio_root / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    _write_outcomes_config(studio_root, '[outcomes]\nledger_path = "~/led.jsonl"\n')

    result = run_phase.get_configured_ledger_path()

    assert result == (home / "led.jsonl").resolve()


# --------------------------------------------------------------------------- #
# Finalize auto-append
# --------------------------------------------------------------------------- #
def test_finalize_appends_rated_run(studio_root):
    ledger = studio_root / "ledger" / "outcomes.jsonl"
    _write_outcomes_config(studio_root, f'[outcomes]\nledger_path = "{ledger}"\n')

    run_id, run_dir = _finalizable_run(studio_root)
    run_phase._write_rating(run_dir, 5, "great", shipped="yes", impact="major", changed="shipped it")

    run_phase.finalize_run(make_finalize_args(run_id=run_id))

    records = [json.loads(x) for x in ledger.read_text().splitlines() if x.strip()]
    assert len(records) == 1
    rec = records[0]
    assert rec["run_id"] == run_id
    assert rec["score"] == 5
    assert rec["shipped"] == "yes"
    assert rec["changed"] == "shipped it"


def test_finalize_appends_unrated_run(studio_root):
    ledger = studio_root / "ledger" / "outcomes.jsonl"
    _write_outcomes_config(studio_root, f'[outcomes]\nledger_path = "{ledger}"\n')

    run_id, _ = _finalizable_run(studio_root)
    run_phase.finalize_run(make_finalize_args(run_id=run_id))

    records = [json.loads(x) for x in ledger.read_text().splitlines() if x.strip()]
    assert len(records) == 1
    rec = records[0]
    assert rec["run_id"] == run_id
    assert rec["verdict"] == "APPROVED"
    assert rec["score"] is None
    assert rec["shipped"] is None
    assert rec["rated_iso"] is None


def test_finalize_no_append_without_config(studio_root):
    """No [outcomes] config → no ledger written at the default location."""
    run_id, _ = _finalizable_run(studio_root)
    run_phase.finalize_run(make_finalize_args(run_id=run_id))

    assert not (studio_root / "knowledge" / "outcomes.jsonl").exists()


def test_refinalize_dedups_same_run(studio_root):
    ledger = studio_root / "ledger" / "outcomes.jsonl"
    _write_outcomes_config(studio_root, f'[outcomes]\nledger_path = "{ledger}"\n')

    run_id, run_dir = _finalizable_run(studio_root)
    run_phase.finalize_run(make_finalize_args(run_id=run_id))

    # Rate, then finalize again: the record refreshes, it does not duplicate.
    run_phase._write_rating(run_dir, 4, "revisited", shipped="partial")
    run_phase.finalize_run(make_finalize_args(run_id=run_id))

    records = [json.loads(x) for x in ledger.read_text().splitlines() if x.strip()]
    assert len(records) == 1
    keys = {(r["repo"], r["run_id"]) for r in records}
    assert len(keys) == 1
    assert records[0]["score"] == 4  # refreshed from the second finalize
    assert records[0]["shipped"] == "partial"


def test_finalize_soft_fails_on_unwritable_ledger(studio_root, capsys):
    """An unwritable ledger path never breaks finalize; run.json is still written."""
    blocker = studio_root / "blocker"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")
    # ledger_path's parent sits under a regular file, so mkdir must fail.
    bad_ledger = blocker / "sub" / "outcomes.jsonl"
    _write_outcomes_config(studio_root, f'[outcomes]\nledger_path = "{bad_ledger}"\n')

    run_id, run_dir = _finalizable_run(studio_root)
    run_phase.finalize_run(make_finalize_args(run_id=run_id))

    meta = run_phase.load_json(run_dir / "run.json")
    assert meta["status"] == "COMPLETED"
    err = capsys.readouterr().err
    assert "Ledger append failed" in err
    assert "import-outcomes" in err

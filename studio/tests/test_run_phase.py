import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RUN_PHASE_PATH = Path(__file__).resolve().parents[1] / "run_phase.py"
sys.path.insert(0, str(RUN_PHASE_PATH.parent))
_spec = importlib.util.spec_from_file_location("run_phase_module", RUN_PHASE_PATH)
run_phase = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(run_phase)


def _prepare_args(**overrides):
    defaults = {
        "phase": "market",
        "text": "Test idea for Studio workflow",
        "budget": "$0-20/mo",
        "max_iterations": 2,
        "role_pack": None,
        "roles": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _finalize_args(**overrides):
    defaults = {
        "phase": "market",
        "run_id": "",
        "status": "completed",
        "summary": None,
        "verdict": "APPROVED",
        "iterations_run": None,
        "hours": 1.25,
        "cost": 0.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _configure_tmp_studio(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STUDIO_ROOT", str(tmp_path))
    _seed_manifest(tmp_path)
    return Path(tmp_path)


def _seed_manifest(studio_root: Path) -> None:
    docs_dir = studio_root / "docs" / "role_prompts"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for role in ("marketing", "design"):
        (docs_dir / f"{role}.md").write_text(
            f"# {role.title()} prompt\n\nUse this space for custom instructions.\n",
            encoding="utf-8",
        )

    manifest = {
        "phases": {
            "studio": {
                "advocate": {"role": "Advocate", "goal": "Goal", "backstory": "Story"},
                "contrarian": {"role": "Contrarian", "goal": "Goal", "backstory": "Story"},
                "integrator": {"role": "Integrator", "goal": "Goal", "backstory": "Story"},
            }
        },
        "roles": {
            "marketing": {
                "title": "Marketing Lead",
                "advocate_focus": "Sell the idea.",
                "contrarian_focus": "Question growth claims.",
                "prompt_doc": "docs/role_prompts/marketing.md",
                "deliverables": ["Hook list"],
                "escalate_on": [],
            },
            "design": {
                "title": "Design Lead",
                "advocate_focus": "Define core loop.",
                "contrarian_focus": "Attack scope.",
                "prompt_doc": "docs/role_prompts/design.md",
                "deliverables": ["Core loop sketch"],
                "escalate_on": [],
            },
        },
        "defaults": {"studio_role_pack": "studio_core"},
    }
    (studio_root / "studio.manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    packs_dir = studio_root / "role_packs"
    packs_dir.mkdir(exist_ok=True)
    (packs_dir / "studio_core.json").write_text(
        json.dumps(
            {
                "name": "studio_core",
                "description": "Default pack",
                "roles": ["marketing"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_prepare_and_finalize_creates_index_and_log(tmp_path, monkeypatch):
    studio_root = _configure_tmp_studio(tmp_path, monkeypatch)

    run_id = run_phase.prepare_run(_prepare_args())
    run_dir = studio_root / "output" / "market" / run_id

    assert run_dir.exists()
    assert (run_dir / "instructions.md").exists()

    # Simulate Cascade-produced artifacts
    (run_dir / "advocate_1.md").write_text("Advocate output", encoding="utf-8")
    (run_dir / "contrarian_1.md").write_text("Contrarian output", encoding="utf-8")
    (run_dir / "summary.md").write_text("Summary output", encoding="utf-8")

    run_phase.finalize_run(_finalize_args(run_id=run_id))

    meta = run_phase.load_json(run_dir / "run.json")
    assert meta["iterations_run"] == 1
    assert meta["hours"] == 1.25

    index_contents = (studio_root / "output/index.md").read_text(encoding="utf-8")
    assert run_id in index_contents

    log_contents = (studio_root / "knowledge/run_log.md").read_text(encoding="utf-8")
    assert run_id in log_contents
    assert "Hours: 1.25" in log_contents


def test_finalize_requires_required_artifacts(tmp_path, monkeypatch):
    studio_root = _configure_tmp_studio(tmp_path, monkeypatch)

    run_id = run_phase.prepare_run(_prepare_args(phase="design"))
    run_dir = studio_root / "output" / "design" / run_id

    # Only summary exists; advocate/contrarian missing
    (run_dir / "summary.md").write_text("Summary only", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        run_phase.finalize_run(
            _finalize_args(
                phase="design",
                run_id=run_id,
                verdict="REJECTED",
                hours=None,
                cost=None,
            )
        )

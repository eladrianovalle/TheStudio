"""Shared fixtures for Studio tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Ensure studio/ is on the import path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Temp directory fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir(tmp_path):
    """A plain temporary directory (no Studio structure)."""
    return tmp_path


@pytest.fixture
def temp_run_dir(tmp_path):
    """A temporary directory simulating a single run directory."""
    run_dir = tmp_path / "run_test_000000"
    run_dir.mkdir()
    return run_dir


# ---------------------------------------------------------------------------
# Studio root fixture
# ---------------------------------------------------------------------------

MINIMAL_MANIFEST = {
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
        "engineering": {
            "title": "Engineering Lead",
            "advocate_focus": "Build architecture.",
            "contrarian_focus": "Flag ops risk.",
            "prompt_doc": "docs/role_prompts/engineering.md",
            "deliverables": ["System outline"],
            "escalate_on": [],
        },
        "test_engineer": {
            "title": "Staff Test Engineer",
            "advocate_focus": "Enforce scenario-first test design.",
            "contrarian_focus": "Hunt AI-TDD anti-patterns.",
            "prompt_doc": "docs/role_prompts/test_engineer.md",
            "deliverables": ["Test specification", "Anti-pattern audit"],
            "escalate_on": [],
        },
    },
    "defaults": {
        "studio_role_pack": "studio_core",
        "role_dependencies": {"engineering": ["test_engineer"]},
    },
}


def _seed_studio_root(root: Path) -> None:
    """Populate *root* with the minimum files needed by run_phase."""
    (root / "output").mkdir(exist_ok=True)
    (root / "knowledge").mkdir(exist_ok=True)
    (root / "config").mkdir(exist_ok=True)

    # Manifest
    (root / "studio.manifest.json").write_text(
        json.dumps(MINIMAL_MANIFEST, indent=2), encoding="utf-8"
    )

    # Role pack
    packs_dir = root / "role_packs"
    packs_dir.mkdir(exist_ok=True)
    (packs_dir / "studio_core.json").write_text(
        json.dumps(
            {"name": "studio_core", "description": "Default pack", "roles": ["marketing", "design", "engineering", "test_engineer"]},
            indent=2,
        ),
        encoding="utf-8",
    )

    # Prompt docs
    docs_dir = root / "docs" / "role_prompts"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for role in ("marketing", "design", "engineering", "test_engineer"):
        (docs_dir / f"{role}.md").write_text(f"# {role.title()} prompt\n")


@pytest.fixture
def studio_root(tmp_path, monkeypatch):
    """A fully seeded temporary Studio root with env vars configured."""
    root = tmp_path / "studio"
    root.mkdir()
    _seed_studio_root(root)

    monkeypatch.setenv("STUDIO_ROOT", str(root))
    monkeypatch.setenv("STUDIO_ARTIFACT_ROOT", str(root))
    monkeypatch.chdir(root)
    return root


# ---------------------------------------------------------------------------
# Arg builders (mirrors run_phase CLI args as SimpleNamespace)
# ---------------------------------------------------------------------------

def make_prepare_args(**overrides) -> SimpleNamespace:
    defaults = {
        "phase": "market",
        "text": "Test idea for Studio workflow",
        "budget": None,
        "max_iterations": 2,
        "role_pack": None,
        "roles": None,
        "scopes": None,
        "no_scopes": True,
        "mode": "deliverables",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def make_finalize_args(**overrides) -> SimpleNamespace:
    defaults = {
        "phase": "market",
        "run_id": "",
        "status": "completed",
        "summary": None,
        "verdict": "APPROVED",
        "iterations_run": None,
        "hours": 1.0,
        "cost": 0.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)

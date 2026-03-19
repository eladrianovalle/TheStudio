"""Unit tests for role_overrides.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from role_overrides import (
    RoleOverrideError,
    apply_role_overrides,
    load_role_overrides,
    validate_role_override,
)
from run_phase_roles import build_role_details

from conftest import MINIMAL_MANIFEST


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_override(project_root: Path, role_name: str, data: dict) -> Path:
    """Write a role override file under .studio/roles/."""
    roles_dir = project_root / ".studio" / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)
    path = roles_dir / f"{role_name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# validate_role_override
# ---------------------------------------------------------------------------

class TestValidateRoleOverride:
    def test_valid_override(self):
        validate_role_override("marketing", {"title": "Custom Title"})

    def test_all_valid_keys(self):
        data = {
            "title": "Custom",
            "advocate_focus": "Custom focus",
            "contrarian_focus": "Custom contrarian",
            "prompt_doc": "custom.md",
            "deliverables": ["D1"],
            "escalate_on": ["E1"],
        }
        validate_role_override("marketing", data)

    def test_empty_override_valid(self):
        validate_role_override("marketing", {})

    def test_rejects_non_dict(self):
        with pytest.raises(RoleOverrideError, match="must be a JSON object"):
            validate_role_override("marketing", ["not", "a", "dict"])

    def test_rejects_unknown_keys(self):
        with pytest.raises(RoleOverrideError, match="unknown keys"):
            validate_role_override("marketing", {"title": "OK", "unknown_key": "bad"})

    def test_rejects_non_list_deliverables(self):
        with pytest.raises(RoleOverrideError, match="must be a list"):
            validate_role_override("marketing", {"deliverables": "not a list"})

    def test_rejects_non_list_escalate_on(self):
        with pytest.raises(RoleOverrideError, match="must be a list"):
            validate_role_override("marketing", {"escalate_on": 42})

    def test_rejects_non_string_title(self):
        with pytest.raises(RoleOverrideError, match="must be a string"):
            validate_role_override("marketing", {"title": 123})

    def test_rejects_non_string_advocate_focus(self):
        with pytest.raises(RoleOverrideError, match="must be a string"):
            validate_role_override("marketing", {"advocate_focus": ["list"]})

    def test_includes_path_in_error(self):
        with pytest.raises(RoleOverrideError, match="/fake/path"):
            validate_role_override(
                "marketing",
                {"bad_key": "x"},
                path=Path("/fake/path/marketing.json"),
            )


# ---------------------------------------------------------------------------
# load_role_overrides
# ---------------------------------------------------------------------------

class TestLoadRoleOverrides:
    def test_returns_empty_when_no_dir(self, tmp_path):
        result = load_role_overrides(tmp_path)
        assert result == {}

    def test_returns_empty_when_dir_empty(self, tmp_path):
        (tmp_path / ".studio" / "roles").mkdir(parents=True)
        result = load_role_overrides(tmp_path)
        assert result == {}

    def test_loads_single_override(self, tmp_path):
        _write_override(tmp_path, "marketing", {"title": "Growth Hacker"})
        result = load_role_overrides(tmp_path)
        assert "marketing" in result
        assert result["marketing"]["title"] == "Growth Hacker"

    def test_loads_multiple_overrides(self, tmp_path):
        _write_override(tmp_path, "marketing", {"title": "Custom Marketing"})
        _write_override(tmp_path, "design", {"advocate_focus": "Custom focus"})
        result = load_role_overrides(tmp_path)
        assert len(result) == 2
        assert "marketing" in result
        assert "design" in result

    def test_raises_on_invalid_json(self, tmp_path):
        roles_dir = tmp_path / ".studio" / "roles"
        roles_dir.mkdir(parents=True)
        (roles_dir / "marketing.json").write_text("{bad json")
        with pytest.raises(RoleOverrideError, match="not valid JSON"):
            load_role_overrides(tmp_path)

    def test_raises_on_invalid_structure(self, tmp_path):
        _write_override(tmp_path, "marketing", {"bad_key": "x"})
        with pytest.raises(RoleOverrideError, match="unknown keys"):
            load_role_overrides(tmp_path)

    def test_ignores_non_json_files(self, tmp_path):
        roles_dir = tmp_path / ".studio" / "roles"
        roles_dir.mkdir(parents=True)
        (roles_dir / "README.md").write_text("# Notes")
        _write_override(tmp_path, "marketing", {"title": "Custom"})
        result = load_role_overrides(tmp_path)
        assert list(result.keys()) == ["marketing"]


# ---------------------------------------------------------------------------
# apply_role_overrides
# ---------------------------------------------------------------------------

class TestApplyRoleOverrides:
    def test_no_overrides_returns_original(self):
        base = {"marketing": {"title": "Base", "advocate_focus": "Sell"}}
        result = apply_role_overrides(base, {})
        assert result == base

    def test_shallow_merge_replaces_key(self):
        base = {"marketing": {"title": "Base", "advocate_focus": "Sell"}}
        overrides = {"marketing": {"title": "Custom"}}
        result = apply_role_overrides(base, overrides)
        assert result["marketing"]["title"] == "Custom"
        assert result["marketing"]["advocate_focus"] == "Sell"

    def test_unmatched_override_ignored(self):
        base = {"marketing": {"title": "Base"}}
        overrides = {"nonexistent": {"title": "Nope"}}
        result = apply_role_overrides(base, overrides)
        assert result == base

    def test_multiple_keys_overridden(self):
        base = {
            "marketing": {
                "title": "Old",
                "advocate_focus": "Old focus",
                "deliverables": ["D1"],
            }
        }
        overrides = {
            "marketing": {
                "title": "New",
                "deliverables": ["D1", "D2", "D3"],
            }
        }
        result = apply_role_overrides(base, overrides)
        assert result["marketing"]["title"] == "New"
        assert result["marketing"]["advocate_focus"] == "Old focus"
        assert result["marketing"]["deliverables"] == ["D1", "D2", "D3"]

    def test_does_not_mutate_original(self):
        base = {"marketing": {"title": "Base"}}
        overrides = {"marketing": {"title": "Custom"}}
        apply_role_overrides(base, overrides)
        assert base["marketing"]["title"] == "Base"


# ---------------------------------------------------------------------------
# Integration: build_role_details with overrides
# ---------------------------------------------------------------------------

class TestBuildRoleDetailsWithOverrides:
    def test_override_changes_advocate_focus(self):
        overrides = {"marketing": {"advocate_focus": "Custom marketing focus"}}
        details = build_role_details(MINIMAL_MANIFEST, ["marketing"], overrides=overrides)
        assert details[0].advocate_focus == "Custom marketing focus"
        assert details[0].title == "Marketing Lead"  # inherited

    def test_override_changes_title(self):
        overrides = {"marketing": {"title": "Growth Hacker"}}
        details = build_role_details(MINIMAL_MANIFEST, ["marketing"], overrides=overrides)
        assert details[0].title == "Growth Hacker"
        assert details[0].advocate_focus == "Sell the idea."  # inherited

    def test_no_override_for_role_unchanged(self):
        overrides = {"design": {"title": "Custom Design"}}
        details = build_role_details(MINIMAL_MANIFEST, ["marketing"], overrides=overrides)
        assert details[0].title == "Marketing Lead"

    def test_none_overrides_no_effect(self):
        details = build_role_details(MINIMAL_MANIFEST, ["marketing"], overrides=None)
        assert details[0].title == "Marketing Lead"

    def test_overrides_applied_to_multiple_roles(self):
        overrides = {
            "marketing": {"title": "Custom Marketing"},
            "design": {"advocate_focus": "Custom design focus"},
        }
        details = build_role_details(
            MINIMAL_MANIFEST, ["marketing", "design"], overrides=overrides
        )
        assert details[0].title == "Custom Marketing"
        assert details[0].advocate_focus == "Sell the idea."  # inherited
        assert details[1].title == "Design Lead"  # inherited
        assert details[1].advocate_focus == "Custom design focus"


# ---------------------------------------------------------------------------
# End-to-end: load from disk + apply
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_override_file_affects_role_spec(self, tmp_path):
        _write_override(tmp_path, "marketing", {
            "advocate_focus": "Project-specific marketing focus",
            "deliverables": ["Custom D1", "Custom D2"],
        })
        overrides = load_role_overrides(tmp_path)
        details = build_role_details(MINIMAL_MANIFEST, ["marketing"], overrides=overrides)
        assert details[0].advocate_focus == "Project-specific marketing focus"
        assert details[0].deliverables == ["Custom D1", "Custom D2"]
        assert details[0].title == "Marketing Lead"  # inherited
        assert details[0].contrarian_focus == "Question growth claims."  # inherited

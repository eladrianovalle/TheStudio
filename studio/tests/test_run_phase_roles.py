"""Unit tests for run_phase_roles.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_phase_roles import (
    RoleConfigError,
    RoleDetails,
    build_role_details,
    collect_role_artifacts,
    default_role_pack_name,
    get_role_spec,
    load_manifest,
    load_role_pack,
    normalize_role_filename,
    parse_iteration_from_filename,
    resolve_role_list,
)

from conftest import MINIMAL_MANIFEST


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------

class TestLoadManifest:
    def test_loads_valid_manifest(self, studio_root):
        manifest = load_manifest(studio_root)
        assert "roles" in manifest
        assert "marketing" in manifest["roles"]

    def test_raises_on_missing_manifest(self, tmp_path):
        with pytest.raises(RoleConfigError, match="not found"):
            load_manifest(tmp_path)

    def test_raises_on_invalid_json(self, tmp_path):
        (tmp_path / "studio.manifest.json").write_text("not valid json {{{")
        with pytest.raises(RoleConfigError, match="not valid JSON"):
            load_manifest(tmp_path)


# ---------------------------------------------------------------------------
# get_role_spec
# ---------------------------------------------------------------------------

class TestGetRoleSpec:
    def test_returns_role_details(self):
        details = get_role_spec(MINIMAL_MANIFEST, "marketing")
        assert isinstance(details, RoleDetails)
        assert details.name == "marketing"
        assert details.title == "Marketing Lead"
        assert details.advocate_focus == "Sell the idea."
        assert details.deliverables == ["Hook list"]

    def test_raises_on_unknown_role(self):
        with pytest.raises(RoleConfigError, match="not defined"):
            get_role_spec(MINIMAL_MANIFEST, "nonexistent")

    def test_defaults_title_to_capitalized_name(self):
        manifest = {"roles": {"test_role": {"advocate_focus": "test"}}}
        details = get_role_spec(manifest, "test_role")
        assert details.title == "Test_Role"

    def test_handles_missing_optional_fields(self):
        manifest = {"roles": {"bare": {"title": "Bare Role"}}}
        details = get_role_spec(manifest, "bare")
        assert details.advocate_focus == ""
        assert details.contrarian_focus == ""
        assert details.prompt_doc == ""
        assert details.deliverables == []
        assert details.escalate_on == []


# ---------------------------------------------------------------------------
# default_role_pack_name
# ---------------------------------------------------------------------------

class TestDefaultRolePackName:
    def test_returns_default_pack(self):
        assert default_role_pack_name(MINIMAL_MANIFEST) == "studio_core"

    def test_raises_when_missing(self):
        with pytest.raises(RoleConfigError, match="missing"):
            default_role_pack_name({})

    def test_raises_on_empty_string(self):
        with pytest.raises(RoleConfigError, match="missing"):
            default_role_pack_name({"defaults": {"studio_role_pack": ""}})


# ---------------------------------------------------------------------------
# load_role_pack
# ---------------------------------------------------------------------------

class TestLoadRolePack:
    def test_loads_valid_pack(self, studio_root):
        pack = load_role_pack(studio_root, "studio_core")
        assert pack["name"] == "studio_core"
        assert "marketing" in pack["roles"]

    def test_raises_on_missing_pack(self, studio_root):
        with pytest.raises(RoleConfigError, match="not found"):
            load_role_pack(studio_root, "nonexistent_pack")

    def test_raises_on_invalid_json(self, studio_root):
        bad_pack = studio_root / "role_packs" / "bad.json"
        bad_pack.write_text("{invalid json")
        with pytest.raises(RoleConfigError, match="invalid JSON"):
            load_role_pack(studio_root, "bad")


# ---------------------------------------------------------------------------
# resolve_role_list
# ---------------------------------------------------------------------------

class TestResolveRoleList:
    def test_base_pack_roles(self):
        pack = {"roles": ["marketing", "design"]}
        result = resolve_role_list(MINIMAL_MANIFEST, pack)
        assert result == ["marketing", "design"]

    def test_add_role(self):
        pack = {"roles": ["marketing"]}
        result = resolve_role_list(MINIMAL_MANIFEST, pack, ["+design"])
        assert result == ["marketing", "design"]

    def test_remove_role(self):
        pack = {"roles": ["marketing", "design"]}
        result = resolve_role_list(MINIMAL_MANIFEST, pack, ["-marketing"])
        assert result == ["design"]

    def test_add_and_remove(self):
        pack = {"roles": ["marketing"]}
        result = resolve_role_list(MINIMAL_MANIFEST, pack, ["+engineering", "-marketing"])
        assert "engineering" in result
        assert "marketing" not in result

    def test_no_duplicate_on_add(self):
        pack = {"roles": ["marketing"]}
        result = resolve_role_list(MINIMAL_MANIFEST, pack, ["+marketing"])
        assert result.count("marketing") == 1

    def test_raises_on_invalid_token(self):
        pack = {"roles": ["marketing"]}
        with pytest.raises(RoleConfigError, match="must start with"):
            resolve_role_list(MINIMAL_MANIFEST, pack, ["marketing"])

    def test_raises_on_unknown_role(self):
        pack = {"roles": ["marketing"]}
        with pytest.raises(RoleConfigError, match="not defined"):
            resolve_role_list(MINIMAL_MANIFEST, pack, ["+nonexistent"])

    def test_empty_overrides(self):
        pack = {"roles": ["marketing"]}
        result = resolve_role_list(MINIMAL_MANIFEST, pack, None)
        assert result == ["marketing"]

    def test_blank_tokens_skipped(self):
        pack = {"roles": ["marketing"]}
        result = resolve_role_list(MINIMAL_MANIFEST, pack, ["", "  ", "+design"])
        assert result == ["marketing", "design"]


# ---------------------------------------------------------------------------
# build_role_details
# ---------------------------------------------------------------------------

class TestBuildRoleDetails:
    def test_builds_multiple(self):
        details = build_role_details(MINIMAL_MANIFEST, ["marketing", "design"])
        assert len(details) == 2
        assert details[0].name == "marketing"
        assert details[1].name == "design"

    def test_raises_on_unknown(self):
        with pytest.raises(RoleConfigError):
            build_role_details(MINIMAL_MANIFEST, ["marketing", "ghost"])


# ---------------------------------------------------------------------------
# normalize_role_filename
# ---------------------------------------------------------------------------

class TestNormalizeRoleFilename:
    def test_advocate(self):
        assert normalize_role_filename("marketing", 1, "advocate") == "advocate--marketing--01.md"

    def test_contrarian(self):
        assert normalize_role_filename("design", 3, "contrarian") == "contrarian--design--03.md"

    def test_spaces_become_dashes(self):
        assert normalize_role_filename("game design", 2, "advocate") == "advocate--game-design--02.md"

    def test_double_digit(self):
        assert normalize_role_filename("qa", 12, "advocate") == "advocate--qa--12.md"


# ---------------------------------------------------------------------------
# parse_iteration_from_filename
# ---------------------------------------------------------------------------

class TestParseIterationFromFilename:
    def test_standard_pattern(self):
        assert parse_iteration_from_filename("advocate--marketing--03.md") == 3

    def test_with_path(self):
        assert parse_iteration_from_filename("some/dir/contrarian--design--07.md") == 7

    def test_no_match_returns_zero(self):
        assert parse_iteration_from_filename("advocate_1.md") == 0

    def test_single_part_returns_zero(self):
        assert parse_iteration_from_filename("summary.md") == 0


# ---------------------------------------------------------------------------
# collect_role_artifacts
# ---------------------------------------------------------------------------

class TestCollectRoleArtifacts:
    def test_finds_matching_files(self, temp_run_dir):
        (temp_run_dir / "advocate--marketing--01.md").write_text("a1")
        (temp_run_dir / "advocate--marketing--02.md").write_text("a2")
        (temp_run_dir / "advocate--design--01.md").write_text("d1")  # different role

        result = collect_role_artifacts(temp_run_dir, "marketing", "advocate")
        assert len(result) == 2
        assert result[0].name == "advocate--marketing--01.md"
        assert result[1].name == "advocate--marketing--02.md"

    def test_returns_empty_when_none(self, temp_run_dir):
        result = collect_role_artifacts(temp_run_dir, "marketing", "advocate")
        assert result == []

    def test_contrarian_kind(self, temp_run_dir):
        (temp_run_dir / "contrarian--qa--01.md").write_text("c1")
        result = collect_role_artifacts(temp_run_dir, "qa", "contrarian")
        assert len(result) == 1

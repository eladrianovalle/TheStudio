"""Tests for studio/setup.py — setup wizard state, config generation, and steps."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import setup


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a minimal project with .studio/ and a copy of studio source."""
    dot_studio = tmp_path / ".studio"
    dot_studio.mkdir()
    (dot_studio / "VERSION").write_text("{}", encoding="utf-8")

    # Copy manifest and role packs so helpers can find them
    source_dir = Path(__file__).resolve().parent.parent
    source_dest = dot_studio / "source"
    source_dest.mkdir()

    manifest_src = source_dir / "studio.manifest.json"
    (source_dest / "studio.manifest.json").write_text(
        manifest_src.read_text(encoding="utf-8"), encoding="utf-8"
    )

    packs_src = source_dir / "role_packs"
    packs_dest = source_dest / "role_packs"
    packs_dest.mkdir()
    for pack_file in packs_src.glob("*.json"):
        (packs_dest / pack_file.name).write_text(
            pack_file.read_text(encoding="utf-8"), encoding="utf-8"
        )

    return tmp_path


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


class TestLoadSetupState:
    def test_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        state = setup.load_setup_state(tmp_path)
        assert state["schema_version"] == setup.SCHEMA_VERSION
        assert state["setup_version"] == 0
        assert state["completed_steps"] == {}

    def test_returns_empty_on_corrupt_json(self, tmp_path: Path) -> None:
        setup_path = tmp_path / ".studio" / setup.SETUP_FILE
        setup_path.parent.mkdir(parents=True)
        setup_path.write_text("not json!", encoding="utf-8")
        state = setup.load_setup_state(tmp_path)
        assert state["completed_steps"] == {}

    def test_returns_empty_on_non_object(self, tmp_path: Path) -> None:
        setup_path = tmp_path / ".studio" / setup.SETUP_FILE
        setup_path.parent.mkdir(parents=True)
        setup_path.write_text("[1, 2, 3]", encoding="utf-8")
        state = setup.load_setup_state(tmp_path)
        assert state["completed_steps"] == {}

    def test_loads_existing(self, tmp_path: Path) -> None:
        setup_path = tmp_path / ".studio" / setup.SETUP_FILE
        setup_path.parent.mkdir(parents=True)
        data = {
            "schema_version": 1,
            "setup_version": 1,
            "completed_steps": {"role_pack": 1},
            "choices": {"role_pack": "studio_core"},
        }
        setup_path.write_text(json.dumps(data), encoding="utf-8")
        state = setup.load_setup_state(tmp_path)
        assert state["completed_steps"]["role_pack"] == 1
        assert state["choices"]["role_pack"] == "studio_core"


class TestSaveSetupState:
    def test_roundtrip(self, tmp_path: Path) -> None:
        (tmp_path / ".studio").mkdir()
        state = setup._empty_state()
        state["choices"]["role_pack"] = "studio_core"
        setup.save_setup_state(tmp_path, state)

        loaded = setup.load_setup_state(tmp_path)
        assert loaded["choices"]["role_pack"] == "studio_core"
        assert loaded["setup_version"] == setup.CURRENT_SETUP_VERSION
        assert "first_setup" in loaded["timestamps"]
        assert "last_setup" in loaded["timestamps"]

    def test_preserves_first_setup(self, tmp_path: Path) -> None:
        (tmp_path / ".studio").mkdir()
        state = setup._empty_state()
        state["timestamps"]["first_setup"] = "2026-01-01T00:00:00Z"
        setup.save_setup_state(tmp_path, state)

        loaded = setup.load_setup_state(tmp_path)
        assert loaded["timestamps"]["first_setup"] == "2026-01-01T00:00:00Z"

    def test_creates_studio_dir(self, tmp_path: Path) -> None:
        state = setup._empty_state()
        setup.save_setup_state(tmp_path, state)
        assert (tmp_path / ".studio" / setup.SETUP_FILE).exists()


# ---------------------------------------------------------------------------
# Pending steps
# ---------------------------------------------------------------------------


class TestPendingSteps:
    def test_all_pending_on_fresh(self) -> None:
        state = setup._empty_state()
        pend = setup.pending_steps(state)
        assert len(pend) == len(setup.SETUP_STEPS)
        assert [s["name"] for s in pend] == [s["name"] for s in setup.SETUP_STEPS]

    def test_none_pending_when_all_completed(self) -> None:
        state = setup._empty_state()
        for step in setup.SETUP_STEPS:
            state["completed_steps"][step["name"]] = step["introduced_at"]
        pend = setup.pending_steps(state)
        assert pend == []

    def test_v1_completed_returns_persona_step(self) -> None:
        """A SETUP.json configured at v1 should surface the v2 persona step."""
        state = setup._empty_state()
        state["setup_version"] = 1
        for step in setup.SETUP_STEPS:
            if step["introduced_at"] <= 1:
                state["completed_steps"][step["name"]] = step["introduced_at"]
        pend = setup.pending_steps(state)
        names = [s["name"] for s in pend]
        assert names == ["persona_customization"]

    def test_detects_new_step(self, monkeypatch: pytest.MonkeyPatch) -> None:
        state = setup._empty_state()
        for step in setup.SETUP_STEPS:
            state["completed_steps"][step["name"]] = step["introduced_at"]
        # Simulate a new step added at version 2
        extended_steps = list(setup.SETUP_STEPS) + [
            {"name": "new_feature", "introduced_at": 2, "label": "New Feature"}
        ]
        monkeypatch.setattr(setup, "SETUP_STEPS", extended_steps)
        pend = setup.pending_steps(state)
        assert len(pend) == 1
        assert pend[0]["name"] == "new_feature"


# ---------------------------------------------------------------------------
# Manifest & pack helpers
# ---------------------------------------------------------------------------


class TestGetManifestRoles:
    def test_returns_roles(self) -> None:
        roles = setup.get_manifest_roles()
        assert "marketing" in roles
        assert "engineering" in roles
        assert "title" in roles["marketing"]

    def test_from_project_source(self, project: Path) -> None:
        studio_dir = project / ".studio" / "source"
        roles = setup.get_manifest_roles(studio_dir)
        assert "marketing" in roles


class TestGetAvailablePacks:
    def test_returns_packs(self) -> None:
        packs = setup.get_available_packs()
        names = {p["name"] for p in packs}
        assert "studio_core" in names
        for pack in packs:
            assert "name" in pack
            assert "description" in pack
            assert "roles" in pack

    def test_from_project_source(self, project: Path) -> None:
        studio_dir = project / ".studio" / "source"
        packs = setup.get_available_packs(studio_dir)
        assert any(p["name"] == "studio_core" for p in packs)


# ---------------------------------------------------------------------------
# Apply: role pack
# ---------------------------------------------------------------------------


class TestApplyRolePack:
    def test_selects_pack(self, project: Path) -> None:
        result = setup.apply_role_pack(project, "studio_core")
        assert result["pack"] == "studio_core"
        assert "marketing" in result["roles"]
        assert "engineering" in result["roles"]

        state = setup.load_setup_state(project)
        assert state["choices"]["role_pack"] == "studio_core"
        assert state["completed_steps"]["role_pack"] == 1

    def test_with_add_override(self, project: Path) -> None:
        result = setup.apply_role_pack(project, "studio_core", ["+ml"])
        assert "ml" in result["roles"]

    def test_with_remove_override(self, project: Path) -> None:
        result = setup.apply_role_pack(project, "studio_core", ["-art"])
        assert "art" not in result["roles"]
        assert "marketing" in result["roles"]

    def test_add_and_remove(self, project: Path) -> None:
        result = setup.apply_role_pack(project, "studio_core", ["+ml", "-art"])
        assert "ml" in result["roles"]
        assert "art" not in result["roles"]

    def test_invalid_pack_raises(self, project: Path) -> None:
        from run_phase_roles import RoleConfigError

        with pytest.raises(RoleConfigError):
            setup.apply_role_pack(project, "nonexistent_pack")

    def test_add_duplicate_no_error(self, project: Path) -> None:
        result = setup.apply_role_pack(project, "studio_core", ["+marketing"])
        assert result["roles"].count("marketing") == 1

    def test_enforces_role_dependencies(self, project: Path) -> None:
        """engineering should auto-inject test_engineer via resolve_role_list."""
        result = setup.apply_role_pack(project, "studio_core", ["-test_engineer"])
        # test_engineer was explicitly removed, so it should stay removed
        assert "test_engineer" not in result["roles"]
        assert "engineering" in result["roles"]


# ---------------------------------------------------------------------------
# Apply: role customization
# ---------------------------------------------------------------------------


class TestApplyRoleCustomization:
    def test_writes_override_file(self, project: Path) -> None:
        custs = {"marketing": {"title": "Custom Marketing Lead"}}
        setup.apply_role_customization(project, custs)
        override_path = project / ".studio" / "roles" / "marketing.json"
        assert override_path.exists()
        data = json.loads(override_path.read_text(encoding="utf-8"))
        assert data["title"] == "Custom Marketing Lead"

    def test_empty_customizations(self, project: Path) -> None:
        setup.apply_role_customization(project, {})
        state = setup.load_setup_state(project)
        assert state["completed_steps"]["role_customization"] == 1

    def test_validates_fields(self, project: Path) -> None:
        from role_overrides import RoleOverrideError

        with pytest.raises(RoleOverrideError, match="unknown keys"):
            setup.apply_role_customization(
                project, {"marketing": {"bad_key": "value"}}
            )

    def test_multiple_roles(self, project: Path) -> None:
        custs = {
            "marketing": {"advocate_focus": "Custom focus"},
            "design": {"title": "Custom Designer"},
        }
        setup.apply_role_customization(project, custs)
        assert (project / ".studio" / "roles" / "marketing.json").exists()
        assert (project / ".studio" / "roles" / "design.json").exists()


# ---------------------------------------------------------------------------
# Apply: scopes
# ---------------------------------------------------------------------------


class TestApplyScopes:
    def test_writes_scopes_toml(self, project: Path) -> None:
        setup.apply_scopes(project)
        toml_path = project / ".studio" / "scopes.toml"
        assert toml_path.exists()
        content = toml_path.read_text(encoding="utf-8")
        assert "[scopes.alignment]" in content
        assert "[scopes.depth]" in content
        assert "[scopes.polish]" in content

    def test_custom_values(self, project: Path) -> None:
        custom = {
            "alignment": {
                "focus": "Quick alignment pass.",
                "max_iterations": 1,
                "debate_mode": "all_roles",
            },
            "depth": {
                "focus": "Deep analysis.",
                "max_iterations": 5,
                "debate_mode": "per_role",
            },
        }
        setup.apply_scopes(project, custom)
        content = (project / ".studio" / "scopes.toml").read_text(encoding="utf-8")
        assert "max_iterations = 5" in content
        assert "max_iterations = 1" in content

        state = setup.load_setup_state(project)
        assert state["choices"]["scopes"]["depth"]["max_iterations"] == 5

    def test_roundtrip_with_scopes_loader(self, project: Path) -> None:
        """Written TOML should be loadable by scopes.load_scopes_config."""
        from scopes import load_scopes_config

        setup.apply_scopes(project)
        toml_path = project / ".studio" / "scopes.toml"
        config = load_scopes_config(toml_path)
        assert len(config.scopes) == 3
        names = [s.name for s in config.scopes]
        assert "alignment" in names

    def test_escapes_quotes_in_focus(self, project: Path) -> None:
        custom = {
            "test": {
                "focus": 'Focus with "quotes" inside.',
                "max_iterations": 1,
            },
        }
        setup.apply_scopes(project, custom)
        content = (project / ".studio" / "scopes.toml").read_text(encoding="utf-8")
        assert '\\"quotes\\"' in content


# ---------------------------------------------------------------------------
# Apply: cleanup
# ---------------------------------------------------------------------------


class TestApplyCleanup:
    def test_writes_settings_toml(self, project: Path) -> None:
        setup.apply_cleanup(project)
        path = project / ".studio" / "config" / "studio_settings.toml"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "ttl_days = 30" in content
        assert "size_limit_mb = 900" in content

    def test_custom_values(self, project: Path) -> None:
        setup.apply_cleanup(project, ttl_days=7, size_limit_mb=500)
        path = project / ".studio" / "config" / "studio_settings.toml"
        content = path.read_text(encoding="utf-8")
        assert "ttl_days = 7" in content
        assert "size_limit_mb = 500" in content

        state = setup.load_setup_state(project)
        assert state["choices"]["cleanup"]["ttl_days"] == 7


# ---------------------------------------------------------------------------
# Batch: defaults
# ---------------------------------------------------------------------------


class TestApplyDefaults:
    def test_applies_all_steps(self, project: Path) -> None:
        state = setup.apply_defaults(project)
        pend = setup.pending_steps(state)
        assert pend == []

    def test_generates_config_files(self, project: Path) -> None:
        setup.apply_defaults(project)
        assert (project / ".studio" / "scopes.toml").exists()
        assert (project / ".studio" / "config" / "studio_settings.toml").exists()
        assert (project / ".studio" / setup.SETUP_FILE).exists()

    def test_idempotent(self, project: Path) -> None:
        state1 = setup.apply_defaults(project)
        state2 = setup.apply_defaults(project)
        assert state1["choices"]["role_pack"] == state2["choices"]["role_pack"]
        pend = setup.pending_steps(state2)
        assert pend == []

    def test_default_pack_is_studio_core(self, project: Path) -> None:
        state = setup.apply_defaults(project)
        assert state["choices"]["role_pack"] == "studio_core"

    def test_marks_persona_step_at_v2(self, project: Path) -> None:
        state = setup.apply_defaults(project)
        assert state["setup_version"] == 2
        assert state["completed_steps"]["persona_customization"] == 2
        assert setup.pending_steps(state) == []
        # Empty defaults => no personas.toml written.
        assert not (project / ".studio" / "personas.toml").exists()


# ---------------------------------------------------------------------------
# Batch: from answers
# ---------------------------------------------------------------------------


class TestApplyFromAnswers:
    def test_full_answers(self, project: Path) -> None:
        answers = {
            "role_pack": "studio_core",
            "role_overrides": ["+ml"],
            "role_customizations": {},
            "scopes": "defaults",
            "cleanup": {"ttl_days": 14, "size_limit_mb": 500},
        }
        state = setup.apply_from_answers(project, answers)
        assert state["choices"]["role_pack"] == "studio_core"
        assert "ml" in state["choices"]["resolved_roles"]
        assert state["choices"]["cleanup"]["ttl_days"] == 14

    def test_partial_answers(self, project: Path) -> None:
        answers = {"role_pack": "studio_core"}
        state = setup.apply_from_answers(project, answers)
        assert state["choices"]["role_pack"] == "studio_core"
        # Other steps not completed
        pend = setup.pending_steps(state)
        pending_names = [s["name"] for s in pend]
        assert "scopes" in pending_names

    def test_persona_customizations_in_answers(self, project: Path) -> None:
        import persona_overrides

        answers = {
            "persona_customizations": {
                "tech": {"advocate": "Rust Systems Architect"},
            },
        }
        state = setup.apply_from_answers(project, answers)
        assert state["choices"]["persona_customizations"]["tech"] == ["advocate"]
        loaded = persona_overrides.load_persona_overrides(project)
        assert loaded == {"tech": {"advocate": "Rust Systems Architect"}}

    def test_custom_scopes_in_answers(self, project: Path) -> None:
        answers = {
            "scopes": {
                "fast": {
                    "focus": "Quick pass.",
                    "max_iterations": 1,
                    "debate_mode": "all_roles",
                },
            },
        }
        state = setup.apply_from_answers(project, answers)
        assert state["choices"]["scopes"]["fast"]["max_iterations"] == 1
        content = (project / ".studio" / "scopes.toml").read_text(encoding="utf-8")
        assert "[scopes.fast]" in content


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------


class TestShowStatus:
    def test_unconfigured(self, tmp_path: Path) -> None:
        output = setup.show_status(tmp_path)
        assert "NOT CONFIGURED" in output
        assert "pending" in output.lower()

    def test_fully_configured(self, project: Path) -> None:
        setup.apply_defaults(project)
        output = setup.show_status(project)
        assert "studio_core" in output
        assert "All steps configured" in output

    def test_shows_role_overrides(self, project: Path) -> None:
        setup.apply_role_pack(project, "studio_core", ["+ml", "-art"])
        output = setup.show_status(project)
        assert "+ml" in output
        assert "-art" in output

    def test_shows_neutral_personas_by_default(self, project: Path) -> None:
        setup.apply_defaults(project)
        output = setup.show_status(project)
        assert "Phase personas: none (using neutral defaults)" in output

    def test_shows_customized_personas(self, project: Path) -> None:
        setup.apply_role_pack(project, "studio_core")
        setup.apply_persona_customization(
            project, {"tech": {"advocate": "Rust Systems Architect"}}
        )
        output = setup.show_status(project)
        assert "Phase personas: tech" in output


# ---------------------------------------------------------------------------
# TOML formatting
# ---------------------------------------------------------------------------


class TestFormatScopesToml:
    def test_basic_format(self) -> None:
        scopes = {
            "test": {
                "focus": "Test scope.",
                "max_iterations": 2,
                "output_budget": 400,
                "debate_mode": "all_roles",
            }
        }
        result = setup._format_scopes_toml(scopes)
        assert "[scopes.test]" in result
        assert 'focus = "Test scope."' in result
        assert "max_iterations = 2" in result
        assert "output_budget = 400" in result
        assert 'debate_mode = "all_roles"' in result

    def test_omits_optional_fields(self) -> None:
        scopes = {"test": {"focus": "Minimal.", "max_iterations": 1}}
        result = setup._format_scopes_toml(scopes)
        assert "output_budget" not in result
        assert "debate_mode" not in result


class TestFormatPersonasToml:
    def test_emits_phase_and_implementer_tables(self) -> None:
        custs = {
            "tech": {
                "advocate": "Arch.",
                "implementer": {
                    "title": "Code Gen",
                    "deliverables": ["A", "B"],
                },
            },
        }
        result = setup._format_personas_toml(custs)
        assert "[tech]" in result
        assert 'advocate = "Arch."' in result
        assert "[tech.implementer]" in result
        assert 'title = "Code Gen"' in result
        assert 'deliverables = ["A", "B"]' in result

    def test_roundtrips_via_tomllib(self) -> None:
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore
        custs = {
            "tech": {
                "advocate": 'A "quoted" \\ value',
                "implementer": {"deliverables": ["x", "y"]},
            },
            "market": {"contrarian": "Skeptic"},
        }
        parsed = tomllib.loads(setup._format_personas_toml(custs))
        assert parsed == custs


class TestSuggestPersonasFromStack:
    def test_rust(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text("[package]", encoding="utf-8")
        suggested = setup.suggest_personas_from_stack(tmp_path)
        assert "Rust" in suggested["tech"]["advocate"]

    def test_js(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        suggested = setup.suggest_personas_from_stack(tmp_path)
        assert "tech" in suggested

    def test_unity_csproj(self, tmp_path: Path) -> None:
        (tmp_path / "Game.csproj").write_text("<Project/>", encoding="utf-8")
        suggested = setup.suggest_personas_from_stack(tmp_path)
        assert "Unity" in suggested["tech"]["advocate"]

    def test_no_stack(self, tmp_path: Path) -> None:
        assert setup.suggest_personas_from_stack(tmp_path) == {}


# ---------------------------------------------------------------------------
# Apply: persona customization
# ---------------------------------------------------------------------------


class TestApplyPersonaCustomization:
    def test_writes_and_roundtrips(self, project: Path) -> None:
        import persona_overrides

        custs = {
            "tech": {
                "advocate": "Rust Systems Architect",
                "contrarian": "Senior Systems SRE",
                "notes": "Hold AI-TDD discipline.",
                "implementer": {
                    "title": "Rust Systems Architect & Code Generator",
                    "deliverables": ["Crate layout", "ECS schedule", "Impl code"],
                },
            },
            "studio": {"integrator": "Systems Integrator & Ops Lead"},
        }
        setup.apply_persona_customization(project, custs)

        path = project / ".studio" / "personas.toml"
        assert path.exists()

        # Round-trips through the persona_overrides loader (contract cross-check).
        loaded = persona_overrides.load_persona_overrides(project)
        assert loaded == custs

        state = setup.load_setup_state(project)
        assert state["completed_steps"]["persona_customization"] == 2
        assert set(state["choices"]["persona_customizations"]["tech"]) == {
            "advocate", "contrarian", "notes", "implementer",
        }

    def test_escapes_quotes_and_backslashes(self, project: Path) -> None:
        import persona_overrides

        custs = {"tech": {"advocate": 'Architect with "quotes" and a \\ slash'}}
        setup.apply_persona_customization(project, custs)
        loaded = persona_overrides.load_persona_overrides(project)
        assert loaded == custs

    def test_empty_writes_no_file_but_marks_step(self, project: Path) -> None:
        setup.apply_persona_customization(project, {})
        assert not (project / ".studio" / "personas.toml").exists()
        state = setup.load_setup_state(project)
        assert state["completed_steps"]["persona_customization"] == 2
        assert state["choices"]["persona_customizations"] == {}

    def test_invalid_customization_propagates(self, project: Path) -> None:
        from persona_overrides import PersonaOverrideError

        with pytest.raises(PersonaOverrideError):
            # integrator is valid only under [studio], not [tech]
            setup.apply_persona_customization(
                project, {"tech": {"integrator": "Nope"}}
            )

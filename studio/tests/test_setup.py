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

    def test_v1_completed_returns_later_steps(self) -> None:
        """A SETUP.json configured at v1 should surface every later step."""
        state = setup._empty_state()
        state["setup_version"] = 1
        for step in setup.SETUP_STEPS:
            if step["introduced_at"] <= 1:
                state["completed_steps"][step["name"]] = step["introduced_at"]
        pend = setup.pending_steps(state)
        names = [s["name"] for s in pend]
        assert names == [
            "persona_customization",
            "unstale_config",
            "smoke_config",
            "implementation_loop_config",
        ]

    def test_v4_state_leaves_exactly_the_new_step_pending(self) -> None:
        """Every installed repo reports this one step until the wizard is re-run."""
        state = setup._empty_state()
        state["setup_version"] = 4
        for step in setup.SETUP_STEPS:
            if step["introduced_at"] <= 4:
                state["completed_steps"][step["name"]] = step["introduced_at"]

        pend = setup.pending_steps(state)

        assert [s["name"] for s in pend] == ["implementation_loop_config"]

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
# The wizard no longer writes .studio/scopes.toml
# ---------------------------------------------------------------------------


class TestScopesNoLongerGenerated:
    """The wizard stopped generating scope config; hand-written files still stand."""

    def test_apply_scopes_is_gone(self) -> None:
        with pytest.raises(ImportError):
            from setup import apply_scopes  # noqa: F401

    def test_defaults_write_no_scopes_toml(self, project: Path) -> None:
        setup.apply_defaults(project)
        assert not (project / ".studio" / "scopes.toml").exists()

    def test_answers_write_no_scopes_toml(self, project: Path) -> None:
        """A leftover `scopes` key in an answers payload writes nothing."""
        setup.apply_from_answers(project, {"scopes": "defaults"})
        assert not (project / ".studio" / "scopes.toml").exists()

    def test_hand_written_scopes_toml_survives_defaults(self, project: Path) -> None:
        """A scopes file someone wrote by hand is the only kind that should exist."""
        scopes_path = project / ".studio" / "scopes.toml"
        original = '[scopes.alignment]\nfocus = "Hand-tuned."\nmax_iterations = 9\n'
        scopes_path.write_text(original, encoding="utf-8")

        setup.apply_defaults(project)

        assert scopes_path.read_text(encoding="utf-8") == original

    def test_stale_scopes_step_in_saved_state_is_inert(self, project: Path) -> None:
        """A SETUP.json from before the step was retired reports nothing pending."""
        setup.apply_defaults(project)
        setup_path = project / ".studio" / setup.SETUP_FILE
        state = json.loads(setup_path.read_text(encoding="utf-8"))
        state["completed_steps"]["scopes"] = 1
        state["choices"]["scopes"] = {"alignment": {"max_iterations": 2}}
        setup_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

        reloaded = setup.load_setup_state(project)
        assert setup.pending_steps(reloaded) == []
        assert "Scopes" not in setup.show_status(project)


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
        assert state["setup_version"] == setup.CURRENT_SETUP_VERSION
        assert state["completed_steps"]["persona_customization"] == 2
        assert setup.pending_steps(state) == []
        # Empty defaults => no personas.toml written.
        assert not (project / ".studio" / "personas.toml").exists()

    def test_marks_unstale_step_at_v3(self, project: Path) -> None:
        state = setup.apply_defaults(project)
        assert state["completed_steps"]["unstale_config"] == 3
        assert setup.pending_steps(state) == []
        # Empty defaults => no unstale.toml written; /unstale self-detects.
        assert not (project / ".studio" / "unstale.toml").exists()

    def test_marks_smoke_step_at_v4(self, project: Path) -> None:
        state = setup.apply_defaults(project)
        assert state["completed_steps"]["smoke_config"] == 4
        assert setup.pending_steps(state) == []
        # Empty defaults => no smoke.toml written; /smoke self-detects.
        assert not (project / ".studio" / "smoke.toml").exists()


# ---------------------------------------------------------------------------
# Batch: from answers
# ---------------------------------------------------------------------------


class TestApplyFromAnswers:
    def test_full_answers(self, project: Path) -> None:
        answers = {
            "role_pack": "studio_core",
            "role_overrides": ["+ml"],
            "role_customizations": {},
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
        assert "cleanup" in pending_names

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

    def test_unstale_config_in_answers(self, project: Path) -> None:
        answers = {
            "unstale_config": {
                "snapshot": {"test_count": "cargo test 2>&1 | tail -3"},
                "audit": {"source_globs": ["src/**/*.rs"]},
            },
        }
        state = setup.apply_from_answers(project, answers)
        assert state["choices"]["unstale_config"]["snapshot"] == ["test_count"]
        content = (project / ".studio" / "unstale.toml").read_text(encoding="utf-8")
        assert "[snapshot]" in content
        assert "cargo test" in content

    def test_smoke_config_in_answers(self, project: Path) -> None:
        answers = {
            "smoke_config": {
                "kind": "web",
                "launch": "npm run dev",
                "golden_path": ["Open the URL", "Create a farm"],
            },
        }
        state = setup.apply_from_answers(project, answers)
        assert state["choices"]["smoke_config"]["kind"] == "web"
        content = (project / ".studio" / "smoke.toml").read_text(encoding="utf-8")
        assert "[smoke]" in content
        assert 'launch = "npm run dev"' in content
        assert "golden_path" in content


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

    def test_shows_unstale_self_detect_by_default(self, project: Path) -> None:
        setup.apply_defaults(project)
        output = setup.show_status(project)
        assert "Unstale audit: self-detect (no override)" in output

    def test_shows_custom_unstale(self, project: Path) -> None:
        setup.apply_role_pack(project, "studio_core")
        setup.apply_unstale_config(
            project, {"snapshot": {"test_count": "cargo test"}}
        )
        output = setup.show_status(project)
        assert "Unstale audit: custom override" in output

    def test_shows_smoke_self_detect_by_default(self, project: Path) -> None:
        setup.apply_defaults(project)
        output = setup.show_status(project)
        assert "Smoke test: self-detect (no override)" in output

    def test_shows_custom_smoke(self, project: Path) -> None:
        setup.apply_role_pack(project, "studio_core")
        setup.apply_smoke_config(project, {"kind": "game"})
        output = setup.show_status(project)
        assert "Smoke test: custom profile (game)" in output


# ---------------------------------------------------------------------------
# TOML formatting
# ---------------------------------------------------------------------------


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

    def test_roundtrips_with_control_chars(self) -> None:
        """A multi-line/tabbed persona value must still produce parseable TOML.

        Regression: the escaper only handled backslash and quote, so a literal
        newline/tab wrote a file tomllib refused to parse on the next load.
        """
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore
        custs = {
            "tech": {
                "notes": "Hold AI-TDD discipline.\nAccount for native\tbuild constraints.\r",
                "implementer": {"deliverables": ["line one\nline two"]},
            },
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


# ---------------------------------------------------------------------------
# Unstale audit config
# ---------------------------------------------------------------------------


class TestSuggestUnstaleFromStack:
    def test_rust(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text("[package]", encoding="utf-8")
        cfg = setup.suggest_unstale_from_stack(tmp_path)
        assert "cargo test" in cfg["snapshot"]["test_count"]
        assert cfg["audit"]["source_globs"] == ["src/**/*.rs"]

    def test_node(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        cfg = setup.suggest_unstale_from_stack(tmp_path)
        assert "src/**/*.ts" in cfg["audit"]["source_globs"]

    def test_unity_csproj(self, tmp_path: Path) -> None:
        (tmp_path / "Game.csproj").write_text("<Project/>", encoding="utf-8")
        cfg = setup.suggest_unstale_from_stack(tmp_path)
        # Unity has no shell test command — count check is skipped.
        assert "test_count" not in cfg["snapshot"]
        assert cfg["audit"]["source_globs"] == ["Assets/Scripts/**/*.cs"]

    def test_go(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module x", encoding="utf-8")
        cfg = setup.suggest_unstale_from_stack(tmp_path)
        assert "go test" in cfg["snapshot"]["test_count"]

    def test_python(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
        cfg = setup.suggest_unstale_from_stack(tmp_path)
        assert "pytest" in cfg["snapshot"]["test_count"]

    def test_no_stack(self, tmp_path: Path) -> None:
        assert setup.suggest_unstale_from_stack(tmp_path) == {}


class TestFormatUnstaleToml:
    def test_basic_format(self) -> None:
        cfg = {
            "snapshot": {"test_count": "cargo test", "module_inventory": "ls | wc -l"},
            "audit": {"doc_globs": ["README.md"], "source_globs": ["src/**/*.rs"]},
        }
        result = setup._format_unstale_toml(cfg)
        assert "[snapshot]" in result
        assert 'test_count = "cargo test"' in result
        assert "[audit]" in result
        assert 'source_globs = ["src/**/*.rs"]' in result

    def test_omits_empty_tables(self) -> None:
        result = setup._format_unstale_toml({"snapshot": {"test_count": "x"}})
        assert "[snapshot]" in result
        assert "[audit]" not in result

    def test_roundtrips_via_tomllib(self) -> None:
        """The Node suggestion's find command has backslashes — must round-trip."""
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore
        cfg = {
            "snapshot": {
                "module_inventory": "find src -type f \\( -name '*.ts' \\) | wc -l",
            },
            "audit": {"doc_globs": ["docs/**/*.md"], "source_globs": ["src/**/*.ts"]},
        }
        parsed = tomllib.loads(setup._format_unstale_toml(cfg))
        assert parsed == cfg


class TestApplyUnstaleConfig:
    def test_writes_and_roundtrips(self, project: Path) -> None:
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore
        cfg = setup.suggest_unstale_from_stack(project) or {
            "snapshot": {"test_count": "cargo test"},
            "audit": {"source_globs": ["src/**/*.rs"]},
        }
        setup.apply_unstale_config(project, cfg)
        path = project / ".studio" / "unstale.toml"
        assert path.exists()
        # File parses as valid TOML.
        tomllib.loads(path.read_text(encoding="utf-8"))
        state = setup.load_setup_state(project)
        assert state["completed_steps"]["unstale_config"] == 3

    def test_empty_writes_no_file_but_marks_step(self, project: Path) -> None:
        setup.apply_unstale_config(project, {})
        assert not (project / ".studio" / "unstale.toml").exists()
        state = setup.load_setup_state(project)
        assert state["completed_steps"]["unstale_config"] == 3
        assert state["choices"]["unstale_config"] == {"snapshot": [], "audit": []}


# ---------------------------------------------------------------------------
# Smoke test config
# ---------------------------------------------------------------------------


class TestSuggestSmokeFromStack:
    def test_node_is_web(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        cfg = setup.suggest_smoke_from_stack(tmp_path)
        assert cfg["kind"] == "web"
        assert cfg["launch"] == "npm run dev"

    def test_rust_is_cli(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text("[package]", encoding="utf-8")
        cfg = setup.suggest_smoke_from_stack(tmp_path)
        assert cfg["kind"] == "cli"
        assert "cargo run" in cfg["launch"]

    def test_unity_is_game_with_no_launch(self, tmp_path: Path) -> None:
        (tmp_path / "Game.csproj").write_text("<Project/>", encoding="utf-8")
        cfg = setup.suggest_smoke_from_stack(tmp_path)
        # Unity stands up via Play mode (MCP), not a shell launch command.
        assert cfg["kind"] == "game"
        assert "launch" not in cfg

    def test_go_is_service(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module x", encoding="utf-8")
        cfg = setup.suggest_smoke_from_stack(tmp_path)
        assert cfg["kind"] == "service"
        assert cfg["launch"] == "go run ."

    def test_python_is_cli_without_launch(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]", encoding="utf-8")
        cfg = setup.suggest_smoke_from_stack(tmp_path)
        assert cfg["kind"] == "cli"
        # Entrypoint module isn't inferable from markers, so launch is left blank.
        assert "launch" not in cfg

    def test_no_stack(self, tmp_path: Path) -> None:
        assert setup.suggest_smoke_from_stack(tmp_path) == {}


class TestFormatSmokeToml:
    def test_basic_format(self) -> None:
        cfg = {
            "kind": "web",
            "launch": "npm run dev",
            "golden_path": ["Open the URL", "Create a farm"],
        }
        result = setup._format_smoke_toml(cfg)
        assert "[smoke]" in result
        assert 'kind = "web"' in result
        assert 'launch = "npm run dev"' in result
        assert 'golden_path = ["Open the URL", "Create a farm"]' in result

    def test_ignores_unknown_keys(self) -> None:
        result = setup._format_smoke_toml({"kind": "cli", "bogus": "x"})
        assert 'kind = "cli"' in result
        assert "bogus" not in result

    def test_roundtrips_via_tomllib(self) -> None:
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore
        cfg = {
            "kind": "service",
            "launch": 'run --flag "quoted" \\ path',
            "build": ["go build ./..."],
            "golden_path": ["Hit /health", "Exercise the main path"],
        }
        parsed = tomllib.loads(setup._format_smoke_toml(cfg))
        assert parsed == {"smoke": cfg}


class TestApplySmokeConfig:
    def test_writes_and_roundtrips(self, project: Path) -> None:
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore
        cfg = setup.suggest_smoke_from_stack(project) or {"kind": "cli"}
        setup.apply_smoke_config(project, cfg)
        path = project / ".studio" / "smoke.toml"
        assert path.exists()
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        assert parsed["smoke"]["kind"] == cfg["kind"]
        state = setup.load_setup_state(project)
        assert state["completed_steps"]["smoke_config"] == 4

    def test_empty_writes_no_file_but_marks_step(self, project: Path) -> None:
        setup.apply_smoke_config(project, {})
        assert not (project / ".studio" / "smoke.toml").exists()
        state = setup.load_setup_state(project)
        assert state["completed_steps"]["smoke_config"] == 4
        assert state["choices"]["smoke_config"] == {"kind": "", "keys": []}


# ---------------------------------------------------------------------------
# Forge gate commands (.studio/implementation_loop.toml)
# ---------------------------------------------------------------------------


# Orkid Garden's real override, byte for byte. It keeps its Unity project in a
# subdirectory, so nothing at its root identifies it and this file is the only reason
# /forge works there at all.
ORKID_OVERRIDE = (
    "# Orkid Garden's overrides for the implementation writer/editor loop.\n"
    "\n"
    "[gate]\n"
    'test_command = "./scripts/run-editmode-tests.sh"\n'
    "static_checks = []\n"
    "require_mutation_check = false\n"
)


def _install_shipped_loop_config(project: Path) -> None:
    """Put Studio's shipped config where an installed snapshot would have it.

    Without this the loader has no shipped file to fall back to, and the test would
    prove less than a real installed repo does.
    """
    shipped = Path(__file__).resolve().parent.parent / "config" / "implementation_loop.toml"
    config_dir = project / ".studio" / "source" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "implementation_loop.toml").write_text(
        shipped.read_text(encoding="utf-8"), encoding="utf-8"
    )


def _resolved_gate(project: Path):
    """The config /forge would resolve in *project*, read as an installed snapshot."""
    from impl_loop import load_loop_config

    return load_loop_config(studio_root=project / ".studio" / "source")


@pytest.fixture
def node_project(project: Path) -> Path:
    """A ``project`` that a root package.json makes detectable as Node."""
    (project / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run", "lint": "eslint ."}}),
        encoding="utf-8",
    )
    _install_shipped_loop_config(project)
    return project


class TestApplyImplementationLoopConfig:
    @pytest.fixture(autouse=True)
    def _no_artifact_root_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # impl_loop honors STUDIO_ARTIFACT_ROOT, which another test may have left set —
        # it would point detection at some entirely different repository.
        monkeypatch.delenv("STUDIO_ARTIFACT_ROOT", raising=False)

    def test_node_repo_gets_its_own_commands(
        self, node_project: Path, capsys: pytest.CaptureFixture
    ) -> None:
        config_path = node_project / ".studio" / "implementation_loop.toml"

        setup.apply_implementation_loop_config(node_project)

        content = config_path.read_text(encoding="utf-8")
        assert 'test_command = "npm test"' in content
        assert 'static_checks = ["eslint"]' in content
        assert "require_mutation_check = false" in content
        assert capsys.readouterr().out == f"Wrote {config_path}: test_command = npm test\n"

    def test_written_file_resolves_to_what_detection_alone_produced(
        self, node_project: Path
    ) -> None:
        """The file is a printout of the detection, not a second opinion about it."""
        detected_only = _resolved_gate(node_project)

        setup.apply_implementation_loop_config(node_project)

        assert _resolved_gate(node_project) == detected_only
        assert detected_only.test_command == "npm test"

    def test_marker_less_repo_writes_nothing_and_prints_the_refusal(
        self, project: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from impl_loop import LoopConfigError

        _install_shipped_loop_config(project)

        setup.apply_implementation_loop_config(project)

        assert not (project / ".studio" / "implementation_loop.toml").exists()
        printed = capsys.readouterr().out
        assert "gate.test_command is not set" in printed
        assert "no marker file Studio recognises is present here" in printed
        assert str(project / ".studio" / "implementation_loop.toml") in printed
        with pytest.raises(LoopConfigError):
            _resolved_gate(project)
        state = setup.load_setup_state(project)
        assert state["choices"]["implementation_loop_config"] == {"status": "undetected"}

    def test_ambiguous_repo_writes_nothing_and_names_both_markers(
        self, project: Path, capsys: pytest.CaptureFixture
    ) -> None:
        from impl_loop import LoopConfigError

        _install_shipped_loop_config(project)
        (project / "Cargo.toml").write_text("[package]", encoding="utf-8")
        (project / "package.json").write_text(
            json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8"
        )

        setup.apply_implementation_loop_config(project)

        assert not (project / ".studio" / "implementation_loop.toml").exists()
        printed = capsys.readouterr().out
        assert "rust (Cargo.toml) and node (package.json) both match" in printed
        with pytest.raises(LoopConfigError):
            _resolved_gate(project)

    def test_never_overwrites_orkid_gardens_own_file(
        self, project: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """The one file keeping /forge alive in the repo that reported the bug."""
        (project / "unity").mkdir()  # the Unity project, invisible to root-only detection
        config_path = project / ".studio" / "implementation_loop.toml"
        config_path.write_text(ORKID_OVERRIDE, encoding="utf-8")

        setup.apply_implementation_loop_config(project)

        assert config_path.read_text(encoding="utf-8") == ORKID_OVERRIDE
        assert capsys.readouterr().out == (
            f"Kept the existing {config_path} — setup never overwrites one.\n"
        )
        state = setup.load_setup_state(project)
        assert state["choices"]["implementation_loop_config"] == {"status": "kept"}

    def test_never_overwrites_even_when_detection_has_an_answer(
        self, node_project: Path
    ) -> None:
        """Detection having something to say is not a licence to replace your file."""
        config_path = node_project / ".studio" / "implementation_loop.toml"
        config_path.write_text(ORKID_OVERRIDE, encoding="utf-8")

        setup.apply_implementation_loop_config(node_project)

        assert config_path.read_text(encoding="utf-8") == ORKID_OVERRIDE
        assert _resolved_gate(node_project).test_command == "./scripts/run-editmode-tests.sh"

    def test_marks_the_step_and_records_the_command(self, node_project: Path) -> None:
        setup.apply_implementation_loop_config(node_project)
        state = setup.load_setup_state(node_project)
        assert state["completed_steps"]["implementation_loop_config"] == 5
        assert state["choices"]["implementation_loop_config"] == {
            "status": "written",
            "test_command": "npm test",
        }

    def test_says_so_when_forge_is_pointed_at_another_repo(
        self, node_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """A redirected artifact root means the written file describes a repo /forge isn't gating."""
        elsewhere = tmp_path / "some-other-repo"
        elsewhere.mkdir()
        monkeypatch.setenv("STUDIO_ARTIFACT_ROOT", str(elsewhere))

        setup.apply_implementation_loop_config(node_project)

        printed = capsys.readouterr().out
        assert f"STUDIO_ARTIFACT_ROOT points /forge at {elsewhere}" in printed
        assert str(node_project) in printed

    def test_no_note_when_the_artifact_root_is_the_target(
        self, node_project: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """The installed layout sets the two to the same directory; that is not worth a note."""
        monkeypatch.setenv("STUDIO_ARTIFACT_ROOT", str(node_project))

        setup.apply_implementation_loop_config(node_project)

        assert "STUDIO_ARTIFACT_ROOT" not in capsys.readouterr().out

    def test_says_so_when_target_points_away_from_the_installs_own_repo(
        self, node_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """--target elsewhere is the same drift as a redirected env var, with no env var set."""
        import impl_loop

        installed_in = tmp_path / "the-installs-own-repo"
        monkeypatch.setattr(impl_loop, "STUDIO_ROOT", installed_in / ".studio" / "source")

        setup.apply_implementation_loop_config(node_project)

        printed = capsys.readouterr().out
        assert f"/forge gates {installed_in}, not {node_project}" in printed
        assert "STUDIO_ARTIFACT_ROOT" not in printed

    def test_no_note_from_a_source_checkout_that_is_installed_nowhere(
        self, node_project: Path, capsys: pytest.CaptureFixture,
    ) -> None:
        """The loader falls back to the source dir there; it gates no consuming repo to name."""
        setup.apply_implementation_loop_config(node_project)

        assert "/forge gates" not in capsys.readouterr().out

    def test_runs_from_an_answers_payload(self, node_project: Path) -> None:
        state = setup.apply_from_answers(node_project, {"implementation_loop_config": {}})
        assert state["choices"]["implementation_loop_config"]["status"] == "written"
        assert (node_project / ".studio" / "implementation_loop.toml").exists()

    def test_defaults_run_the_step(self, project: Path) -> None:
        state = setup.apply_defaults(project)
        assert state["completed_steps"]["implementation_loop_config"] == 5
        assert setup.pending_steps(state) == []
        # Nothing detectable at this fixture's root, so nothing is written.
        assert not (project / ".studio" / "implementation_loop.toml").exists()

    def test_status_row_names_the_detected_command(self, node_project: Path) -> None:
        setup.apply_defaults(node_project)
        # Whole line, not a substring: the row is the only place a person sees which
        # command /forge will run, so its wording is the thing under test.
        assert (
            "  Forge gates: npm test (written to .studio/implementation_loop.toml)"
            in setup.show_status(node_project).splitlines()
        )

    def test_status_row_says_when_nothing_was_detected(self, project: Path) -> None:
        setup.apply_defaults(project)
        assert (
            "  Forge gates: none detected — /forge refuses until you write "
            ".studio/implementation_loop.toml" in setup.show_status(project).splitlines()
        )

    def test_status_row_says_when_your_own_file_was_kept(self, project: Path) -> None:
        (project / ".studio" / "implementation_loop.toml").write_text(
            ORKID_OVERRIDE, encoding="utf-8"
        )
        setup.apply_defaults(project)
        assert (
            "  Forge gates: your own .studio/implementation_loop.toml (left alone)"
            in setup.show_status(project).splitlines()
        )

"""Tests for project-local phase persona overrides (persona_overrides.py)."""
from __future__ import annotations

import copy

import pytest

from persona_overrides import (
    PersonaOverrideError,
    apply_persona_overrides,
    load_persona_overrides,
    validate_persona_overrides,
)
from run_phase import PHASE_DETAILS


def _write_personas(root, text):
    studio_dir = root / ".studio"
    studio_dir.mkdir(parents=True, exist_ok=True)
    (studio_dir / "personas.toml").write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------

class TestLoad:
    def test_absent_file_returns_empty(self, tmp_path):
        assert load_persona_overrides(tmp_path) == {}

    def test_valid_file_parsed(self, tmp_path):
        _write_personas(
            tmp_path,
            "[tech]\n"
            'advocate = "Rust Systems Architect"\n'
            "\n"
            "[tech.implementer]\n"
            'title = "Rust Systems Architect & Code Generator"\n'
            'deliverables = ["Crate layout", "ECS schedule"]\n',
        )
        data = load_persona_overrides(tmp_path)
        assert data["tech"]["advocate"] == "Rust Systems Architect"
        assert data["tech"]["implementer"]["title"] == (
            "Rust Systems Architect & Code Generator"
        )
        assert data["tech"]["implementer"]["deliverables"] == [
            "Crate layout",
            "ECS schedule",
        ]


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

class TestValidate:
    def test_unknown_phase(self):
        with pytest.raises(PersonaOverrideError):
            validate_persona_overrides({"bogus": {"advocate": "x"}})

    def test_unknown_key(self):
        with pytest.raises(PersonaOverrideError):
            validate_persona_overrides({"tech": {"wizard": "x"}})

    def test_integrator_under_tech(self):
        with pytest.raises(PersonaOverrideError):
            validate_persona_overrides({"tech": {"integrator": "x"}})

    def test_implementer_under_studio(self):
        with pytest.raises(PersonaOverrideError):
            validate_persona_overrides({"studio": {"implementer": {"title": "x"}}})

    def test_non_string_advocate(self):
        with pytest.raises(PersonaOverrideError):
            validate_persona_overrides({"tech": {"advocate": 42}})

    def test_non_list_deliverables(self):
        with pytest.raises(PersonaOverrideError):
            validate_persona_overrides(
                {"tech": {"implementer": {"deliverables": "not-a-list"}}}
            )

    def test_valid_passes(self):
        # Should not raise.
        validate_persona_overrides(
            {
                "tech": {
                    "advocate": "Rust Systems Architect",
                    "implementer": {"title": "t", "deliverables": ["a", "b"]},
                },
                "studio": {"integrator": "Systems Integrator"},
            }
        )


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

class TestApply:
    def test_override_advocate_only_inherits_rest(self):
        overrides = {"tech": {"advocate": "Rust Systems Architect"}}
        merged = apply_persona_overrides(PHASE_DETAILS, overrides)

        assert merged["tech"]["advocate"] == "Rust Systems Architect"
        # contrarian / notes / implementer inherit defaults.
        assert merged["tech"]["contrarian"] == PHASE_DETAILS["tech"]["contrarian"]
        assert merged["tech"]["notes"] == PHASE_DETAILS["tech"]["notes"]
        assert merged["tech"]["implementer"] == PHASE_DETAILS["tech"]["implementer"]

    def test_override_implementer_title_only_inherits_deliverables(self):
        overrides = {"tech": {"implementer": {"title": "Custom Title"}}}
        merged = apply_persona_overrides(PHASE_DETAILS, overrides)

        assert merged["tech"]["implementer"]["title"] == "Custom Title"
        assert (
            merged["tech"]["implementer"]["deliverables"]
            == PHASE_DETAILS["tech"]["implementer"]["deliverables"]
        )

    def test_unknown_phase_ignored(self):
        overrides = {"nope": {"advocate": "x"}}
        merged = apply_persona_overrides(PHASE_DETAILS, overrides)
        assert "nope" not in merged
        assert merged["tech"] == PHASE_DETAILS["tech"]

    def test_empty_overrides_returns_base(self):
        assert apply_persona_overrides(PHASE_DETAILS, {}) is PHASE_DETAILS

    def test_base_not_mutated(self):
        snapshot = copy.deepcopy(PHASE_DETAILS)
        overrides = {
            "tech": {
                "advocate": "Rust Systems Architect",
                "implementer": {"title": "Custom Title"},
            }
        }
        apply_persona_overrides(PHASE_DETAILS, overrides)
        assert PHASE_DETAILS == snapshot
        # Spot-check the neutral default survived.
        assert "Technical Architect" in PHASE_DETAILS["tech"]["advocate"]

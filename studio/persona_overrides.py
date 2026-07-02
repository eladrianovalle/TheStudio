"""
Project-local phase persona overrides.

Loads ``.studio/personas.toml`` and merges per-phase persona definitions over
the shipped ``PHASE_DETAILS`` defaults using shallow key-level replacement:
an overridden key replaces the default, unspecified keys inherit.

This is the single-phase analogue of ``role_overrides.py`` (which customizes
studio multi-role personas). It lets a project tailor the advocate /
contrarian / implementer / integrator personas for the market, design, tech,
and studio phases without editing the shipped defaults — e.g. a Rust codebase
swapping the tech advocate's default "Technical Architect" for a
"Rust Systems Architect".

File schema (all tables and keys optional; absent keys inherit defaults)::

    [tech]
    advocate = "Rust Systems Architect — define a performant ECS architecture."
    contrarian = "Senior Systems SRE — flag perf and determinism risks."
    notes = "Hold AI-TDD discipline; account for native build constraints."

    [tech.implementer]
    title = "Rust Systems Architect & Code Generator"
    deliverables = ["Crate layout", "ECS schedule", "Test specs", "Impl code"]

    [studio]
    integrator = "Systems Integrator & Ops Lead — merge vision + constraints."

``integrator`` is valid only under ``[studio]``; ``implementer`` is valid only
under the non-studio phases (market, design, tech).
"""
from __future__ import annotations

from config_loading import tomllib

import copy
from pathlib import Path
from typing import Dict, Optional


PERSONAS_FILENAME = "personas.toml"

# Phases that own an `implementer` table (and never an `integrator`).
_IMPLEMENTER_PHASES = frozenset({"market", "design", "tech"})
# Phases that own an `integrator` key (and never an `implementer`).
_INTEGRATOR_PHASES = frozenset({"studio"})
_VALID_PHASES = _IMPLEMENTER_PHASES | _INTEGRATOR_PHASES

# Per-phase string-valued persona keys allowed for every phase.
_COMMON_STRING_KEYS = frozenset({"advocate", "contrarian", "notes"})
# Keys allowed inside an `[phase.implementer]` table.
_IMPLEMENTER_KEYS = frozenset({"title", "deliverables"})


class PersonaOverrideError(RuntimeError):
    """Raised when a persona override file is invalid."""


def _personas_path(project_root: Path) -> Path:
    return Path(project_root) / ".studio" / PERSONAS_FILENAME


def load_persona_overrides(project_root: Path) -> Dict[str, Dict]:
    """Load ``.studio/personas.toml`` into a ``{phase: {fields}}`` dict.

    Returns an empty dict when the file is absent. Raises
    ``PersonaOverrideError`` on malformed TOML or failed validation.
    """
    path = _personas_path(project_root)
    if not path.is_file():
        return {}

    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise PersonaOverrideError(
            f"Persona overrides at {path} are not valid TOML: {exc}"
        ) from exc

    validate_persona_overrides(data, path)
    return data


def validate_persona_overrides(
    data: Dict, path: Optional[Path] = None
) -> None:
    """Validate structural correctness of persona overrides.

    Raises ``PersonaOverrideError`` on unknown phase/key, wrong type, or a
    misplaced ``integrator`` / ``implementer`` table.
    """
    loc = f" at {path}" if path else ""

    if not isinstance(data, dict):
        raise PersonaOverrideError(
            f"Persona overrides{loc} must be a table, got {type(data).__name__}."
        )

    unknown_phases = set(data.keys()) - _VALID_PHASES
    if unknown_phases:
        raise PersonaOverrideError(
            f"Persona overrides{loc} reference unknown phase(s): "
            f"{', '.join(sorted(unknown_phases))}. "
            f"Valid phases: {', '.join(sorted(_VALID_PHASES))}."
        )

    for phase, fields in data.items():
        ploc = f" for phase '{phase}'{loc}"
        if not isinstance(fields, dict):
            raise PersonaOverrideError(
                f"Persona override{ploc} must be a table, "
                f"got {type(fields).__name__}."
            )

        allowed = set(_COMMON_STRING_KEYS)
        if phase in _IMPLEMENTER_PHASES:
            allowed.add("implementer")
        if phase in _INTEGRATOR_PHASES:
            allowed.add("integrator")

        unknown_keys = set(fields.keys()) - allowed
        if unknown_keys:
            raise PersonaOverrideError(
                f"Persona override{ploc} has unknown key(s): "
                f"{', '.join(sorted(unknown_keys))}. "
                f"Valid keys: {', '.join(sorted(allowed))}."
            )

        for key in _COMMON_STRING_KEYS | {"integrator"}:
            if key in fields and not isinstance(fields[key], str):
                raise PersonaOverrideError(
                    f"Persona override{ploc}: '{key}' must be a string."
                )

        impl = fields.get("implementer")
        if impl is not None:
            _validate_implementer(impl, ploc)


def _validate_implementer(impl: object, ploc: str) -> None:
    if not isinstance(impl, dict):
        raise PersonaOverrideError(
            f"Persona override{ploc}: 'implementer' must be a table, "
            f"got {type(impl).__name__}."
        )
    unknown = set(impl.keys()) - _IMPLEMENTER_KEYS
    if unknown:
        raise PersonaOverrideError(
            f"Persona override{ploc}: implementer has unknown key(s): "
            f"{', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(_IMPLEMENTER_KEYS))}."
        )
    if "title" in impl and not isinstance(impl["title"], str):
        raise PersonaOverrideError(
            f"Persona override{ploc}: implementer 'title' must be a string."
        )
    if "deliverables" in impl:
        deliverables = impl["deliverables"]
        if not isinstance(deliverables, list) or not all(
            isinstance(d, str) for d in deliverables
        ):
            raise PersonaOverrideError(
                f"Persona override{ploc}: implementer 'deliverables' must be "
                f"a list of strings."
            )


def apply_persona_overrides(
    base: Dict[str, Dict], overrides: Dict[str, Dict]
) -> Dict[str, Dict]:
    """Return a new ``PHASE_DETAILS``-shaped dict with overrides merged in.

    Per-phase shallow key-level replacement; the nested ``implementer`` table
    is merged one level deeper so ``title`` and ``deliverables`` override
    independently. Overrides for phases absent from ``base`` are ignored.
    ``base`` is never mutated.
    """
    if not overrides:
        return base

    merged: Dict[str, Dict] = {}
    for phase, base_fields in base.items():
        override = overrides.get(phase)
        if not override:
            merged[phase] = copy.deepcopy(base_fields)
            continue

        new_fields = copy.deepcopy(base_fields)
        for key, value in override.items():
            if key == "implementer" and isinstance(
                new_fields.get("implementer"), dict
            ):
                new_fields["implementer"] = {
                    **new_fields["implementer"],
                    **value,
                }
            else:
                new_fields[key] = value
        merged[phase] = new_fields

    return merged

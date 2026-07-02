"""
Project-local role overrides.

Loads overlay files from ``.studio/roles/*.json`` and merges them with
base manifest roles using shallow key-level replacement: override keys
replace the base, unspecified keys inherit from the manifest.

Each override file must be named ``<role_name>.json`` and contain a flat
JSON object with any subset of the standard role keys (title,
advocate_focus, contrarian_focus, prompt_doc, deliverables, escalate_on).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


ROLES_DIRNAME = "roles"


class RoleOverrideError(RuntimeError):
    """Raised when a role override file is invalid."""


_VALID_KEYS = frozenset({
    "title",
    "advocate_focus",
    "contrarian_focus",
    "prompt_doc",
    "deliverables",
    "escalate_on",
})


def _overrides_dir(project_root: Path) -> Path:
    return project_root / ".studio" / ROLES_DIRNAME


def load_role_overrides(project_root: Path) -> Dict[str, Dict]:
    """Load all role override files from ``.studio/roles/``.

    Returns a dict mapping role name -> override fields.
    """
    overrides_path = _overrides_dir(project_root)
    if not overrides_path.is_dir():
        return {}

    result: Dict[str, Dict] = {}
    for path in sorted(overrides_path.glob("*.json")):
        role_name = path.stem
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RoleOverrideError(
                f"Role override '{role_name}' at {path} is not valid JSON: {exc}"
            ) from exc
        validate_role_override(role_name, data, path)
        result[role_name] = data

    return result


def validate_role_override(
    role_name: str, data: Dict, path: Optional[Path] = None
) -> None:
    """Validate structural correctness of a role override.

    Raises ``RoleOverrideError`` on invalid structure.
    """
    loc = f" at {path}" if path else ""

    if not isinstance(data, dict):
        raise RoleOverrideError(
            f"Role override '{role_name}'{loc} must be a JSON object, "
            f"got {type(data).__name__}."
        )

    unknown = set(data.keys()) - _VALID_KEYS
    if unknown:
        raise RoleOverrideError(
            f"Role override '{role_name}'{loc} has unknown keys: "
            f"{', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(_VALID_KEYS))}."
        )

    # Type-check list fields
    for key in ("deliverables", "escalate_on"):
        if key in data and not isinstance(data[key], list):
            raise RoleOverrideError(
                f"Role override '{role_name}'{loc}: '{key}' must be a list."
            )

    # Type-check string fields
    for key in ("title", "advocate_focus", "contrarian_focus", "prompt_doc"):
        if key in data and not isinstance(data[key], str):
            raise RoleOverrideError(
                f"Role override '{role_name}'{loc}: '{key}' must be a string."
            )


def apply_role_overrides(
    manifest_roles: Dict[str, Dict], overrides: Dict[str, Dict]
) -> Dict[str, Dict]:
    """Return a new roles dict with overrides shallow-merged onto base roles.

    Override keys replace the base value; unspecified keys inherit.
    Overrides for roles not in the manifest are ignored (they may be
    project-specific roles the user hasn't added to a pack yet).
    """
    if not overrides:
        return manifest_roles

    merged = {}
    for role_name, base_data in manifest_roles.items():
        override = overrides.get(role_name)
        if override:
            merged[role_name] = {**base_data, **override}
        else:
            merged[role_name] = base_data
    return merged

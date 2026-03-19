from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from role_overrides import apply_role_overrides


MANIFEST_FILENAME = "studio.manifest.json"
ROLE_PACKS_DIRNAME = "role_packs"


@dataclass(frozen=True)
class RoleDetails:
    name: str
    title: str
    advocate_focus: str
    contrarian_focus: str
    prompt_doc: str
    deliverables: List[str]
    escalate_on: List[str]


class RoleConfigError(RuntimeError):
    """Raised when the manifest or role packs are misconfigured."""


def _manifest_path(studio_root: Path) -> Path:
    return studio_root / MANIFEST_FILENAME


def _packs_dir(studio_root: Path) -> Path:
    return studio_root / ROLE_PACKS_DIRNAME


def load_manifest(studio_root: Path) -> Dict:
    path = _manifest_path(studio_root)
    if not path.exists():
        raise RoleConfigError(f"Expected manifest at {path}, but it was not found.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RoleConfigError(f"Manifest at {path} is not valid JSON: {exc}") from exc


def get_role_spec(manifest: Dict, role_name: str) -> RoleDetails:
    roles = manifest.get("roles") or {}
    data = roles.get(role_name)
    if not data:
        raise RoleConfigError(f"Role '{role_name}' is not defined in the manifest.")
    return RoleDetails(
        name=role_name,
        title=data.get("title", role_name.title()),
        advocate_focus=data.get("advocate_focus", ""),
        contrarian_focus=data.get("contrarian_focus", ""),
        prompt_doc=data.get("prompt_doc", ""),
        deliverables=list(data.get("deliverables") or []),
        escalate_on=list(data.get("escalate_on") or []),
    )


def default_role_pack_name(manifest: Dict) -> str:
    defaults = manifest.get("defaults") or {}
    pack = defaults.get("studio_role_pack")
    if not pack:
        raise RoleConfigError("Manifest is missing defaults.studio_role_pack.")
    return pack


def load_role_pack(studio_root: Path, pack_name: str) -> Dict:
    pack_path = _packs_dir(studio_root) / f"{pack_name}.json"
    if not pack_path.exists():
        raise RoleConfigError(f"Role pack '{pack_name}' not found at {pack_path}.")
    try:
        return json.loads(pack_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RoleConfigError(f"Role pack '{pack_name}' is invalid JSON: {exc}") from exc


def _get_role_dependencies(manifest: Dict) -> Dict[str, List[str]]:
    """Return the role_dependencies map from manifest defaults."""
    defaults = manifest.get("defaults") or {}
    return dict(defaults.get("role_dependencies") or {})


def resolve_role_list(
    manifest: Dict,
    pack_data: Dict,
    overrides: Sequence[str] | None = None,
) -> List[str]:
    overrides = overrides or []
    allowed_roles = set((manifest.get("roles") or {}).keys())
    selected = list(pack_data.get("roles") or [])
    explicitly_removed: set[str] = set()
    for token in overrides:
        token = token.strip()
        if not token:
            continue
        if token[0] not in {"+", "-"}:
            raise RoleConfigError(
                f"Role override '{token}' must start with '+' (include) or '-' (exclude)."
            )
        role = token[1:]
        if role not in allowed_roles:
            raise RoleConfigError(f"Role '{role}' is not defined in the manifest.")
        if token[0] == "+":
            if role not in selected:
                selected.append(role)
        else:
            explicitly_removed.add(role)
            selected = [existing for existing in selected if existing != role]

    # Enforce role dependencies: if a role is present, its co-required
    # roles are injected immediately after it (unless explicitly removed).
    deps = _get_role_dependencies(manifest)
    injected: List[str] = []
    for role in selected:
        injected.append(role)
        for dep in deps.get(role, []):
            if dep not in selected and dep not in injected and dep not in explicitly_removed and dep in allowed_roles:
                injected.append(dep)
    return injected


def build_role_details(
    manifest: Dict,
    role_names: Sequence[str],
    overrides: Optional[Dict[str, Dict]] = None,
) -> List[RoleDetails]:
    if overrides:
        manifest = {**manifest, "roles": apply_role_overrides(manifest.get("roles") or {}, overrides)}
    return [get_role_spec(manifest, name) for name in role_names]


def normalize_role_filename(
    role: str, iteration: int, kind: str, scope: str | None = None
) -> str:
    slug = role.replace(" ", "-")
    if scope:
        return f"{kind}--{slug}--{scope}-{iteration:02d}.md"
    return f"{kind}--{slug}--{iteration:02d}.md"


def parse_role_filename(filename: str) -> Tuple[str, str, str | None, int]:
    """Parse a role artifact filename into (kind, role, scope, iteration).

    Handles both flat (``kind--role--NN.md``) and scoped
    (``kind--role--scope-NN.md``) patterns.  Returns ``("", "", None, 0)``
    for filenames that don't match.
    """
    stem = filename.split("/")[-1]
    parts = stem.split("--")
    if len(parts) < 3:
        return ("", "", None, 0)
    kind = parts[0]
    role = parts[1]
    iter_part = parts[-1].split(".")[0]
    scope: str | None = None
    if "-" in iter_part:
        scope, iter_str = iter_part.rsplit("-", 1)
    else:
        iter_str = iter_part
    try:
        iteration = int(iter_str)
    except ValueError:
        iteration = 0
    return (kind, role, scope, iteration)


def parse_iteration_from_filename(filename: str) -> int:
    """Return just the iteration number from a role artifact filename."""
    return parse_role_filename(filename)[3]


def collect_role_artifacts(run_dir: Path, role: str, kind: str) -> List[Path]:
    slug = role.replace(" ", "-")
    pattern = f"{kind}--{slug}--*.md"
    return sorted(run_dir.glob(pattern))

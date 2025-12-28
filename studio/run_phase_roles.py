from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


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


def resolve_role_list(
    manifest: Dict,
    pack_data: Dict,
    overrides: Sequence[str] | None = None,
) -> List[str]:
    overrides = overrides or []
    allowed_roles = set((manifest.get("roles") or {}).keys())
    selected = list(pack_data.get("roles") or [])
    for token in overrides:
        if not token:
            continue
        token = token.strip()
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
            selected = [existing for existing in selected if existing != role]
    return selected


def build_role_details(manifest: Dict, role_names: Sequence[str]) -> List[RoleDetails]:
    return [get_role_spec(manifest, name) for name in role_names]


def normalize_role_filename(role: str, iteration: int, kind: str) -> str:
    slug = role.replace(" ", "-")
    return f"{kind}--{slug}--{iteration:02d}.md"


def parse_iteration_from_filename(filename: str) -> int:
    # Expected pattern: kind--role--NN.md
    stem = filename.split("/")[-1]
    parts = stem.split("--")
    if len(parts) < 3:
        return 0
    iteration_part = parts[-1].split(".")[0]
    try:
        return int(iteration_part)
    except ValueError:
        return 0


def collect_role_artifacts(run_dir: Path, role: str, kind: str) -> List[Path]:
    slug = role.replace(" ", "-")
    pattern = f"{kind}--{slug}--*.md"
    return sorted(run_dir.glob(pattern))

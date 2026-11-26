from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from config_loading import tomllib
from impl_loop import project_config_root

PACKS_DIR = Path(__file__).resolve().parent / "packs"
DEPARTMENT_KEYS = ("asset_command", "routes")
BINARY_ASSETS_SHOWN = 10
OUTPUT_QUOTED_CHARACTERS = 80


class PackConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Department:
    pack: dict
    name: str
    asset_command: str
    routes: list

    @property
    def label(self) -> str:
        return f"{self.pack['name']}.{self.name}"

    @property
    def contract(self) -> dict:
        return self.pack["departments"][self.name]


class DepartmentResult(NamedTuple):
    problems: list
    stdout: str
    asset_count: int


def shipped_pack_names() -> list[str]:
    return sorted(path.parent.name for path in PACKS_DIR.glob("*/pack.json"))


def load_pack(name: str) -> dict:
    return json.loads((PACKS_DIR / name / "pack.json").read_text(encoding="utf-8"))


def pack_doc_path(pack: dict) -> Path:
    return PACKS_DIR / pack["name"] / pack["doc"]


def declared_departments(data: dict, config_path: Path) -> list[Department]:
    packs_table = data.get("packs")
    if packs_table is None:
        return []
    shipped = shipped_pack_names()

    def refusal(problem: str) -> PackConfigError:
        return PackConfigError(f"{config_path}: {problem} Shipped packs: {', '.join(shipped)}.")

    if not isinstance(packs_table, dict):
        raise refusal("[packs] must be a table.")
    departments: list[Department] = []
    for pack_name, pack_table in packs_table.items():
        if pack_name not in shipped:
            raise refusal(f"[packs.{pack_name}] names a pack Studio does not ship.")
        if not isinstance(pack_table, dict):
            raise refusal(f"[packs.{pack_name}] must be a table.")
        pack = load_pack(pack_name)
        known_departments = pack["departments"]
        for department_name in pack_table:
            if department_name not in known_departments:
                raise refusal(
                    f"[packs.{pack_name}.{department_name}]: the {pack_name} pack has no department "
                    f"{department_name} ({', '.join(sorted(known_departments))})."
                )
        for department_name, contract in known_departments.items():
            section = f"[packs.{pack_name}.{department_name}]"
            declaration = pack_table.get(department_name)
            if not isinstance(declaration, dict):
                raise refusal(f"{section} is missing; every department of a pack you use needs one.")
            unknown_keys = sorted(key for key in declaration if key not in DEPARTMENT_KEYS)
            if unknown_keys:
                raise refusal(f"{section} has a key it does not take: {unknown_keys[0]}.")
            asset_command = declaration.get("asset_command")
            if not isinstance(asset_command, str) or not asset_command.strip():
                raise refusal(f"{section} needs a non-empty asset_command.")
            routes = declaration.get("routes")
            if not isinstance(routes, list) or not routes:
                raise refusal(f"{section} needs a non-empty routes list.")
            for route in routes:
                if route not in contract["routes"]:
                    raise refusal(
                        f"{section}: route {json.dumps(route)} is not one of the {pack_name} pack's "
                        f"routes ({', '.join(contract['routes'])})."
                    )
            departments.append(Department(pack, department_name, asset_command, list(routes)))
    return departments


def load_declaration(config_path: Path) -> list[Department]:
    try:
        with open(config_path, "rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise PackConfigError(f"{config_path}: not valid TOML: {error}") from error
    return declared_departments(data, config_path)


def _is_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def _shown(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _metric_problem(measurement: object) -> str | None:
    if not isinstance(measurement, dict) or not _is_number(measurement.get("value")):
        return "has no numeric value"
    value = measurement["value"]
    limits = {name: measurement[name] for name in ("max", "min") if name in measurement}
    if not limits or not all(_is_number(limit) for limit in limits.values()):
        return "has no max or min"
    maximum = limits.get("max")
    minimum = limits.get("min")
    if maximum is not None and minimum is not None and minimum > maximum:
        return f"min {minimum} is above max {maximum}"
    if maximum is not None and value > maximum:
        return f"is {value}, above its max {maximum}"
    if minimum is not None and value < minimum:
        return f"is {value}, below its min {minimum}"
    return None


def _asset_problems(asset_id: str, asset: dict, department: Department) -> list[str]:
    problems: list[str] = []
    kinds = department.contract["kinds"]
    kind = asset.get("kind")
    known_kind = isinstance(kind, str) and kind in kinds
    if not known_kind:
        problems.append(
            f'{asset_id}: kind "{_shown(kind)}" is not one the {department.pack["name"]} pack knows '
            f"({', '.join(sorted(kinds))})"
        )
    route = asset.get("route")
    if not (isinstance(route, str) and route in department.routes):
        problems.append(
            f"{asset_id}: route \"{_shown(route)}\" is not in this repository's routes "
            f"({', '.join(department.routes)})"
        )
    metrics = asset.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    required_metrics = kinds[kind] if known_kind else []
    for metric in required_metrics:
        if metric not in metrics:
            problems.append(f"{asset_id}: kind {kind} needs metric {metric}, which the report does not have")
    for metric, measurement in metrics.items():
        problem = _metric_problem(measurement)
        if problem is not None:
            problems.append(f"{asset_id}: metric {metric} {problem}")
    return problems


def report_problems(report: object, department: Department) -> list[str]:
    if not isinstance(report, dict) or not isinstance(report.get("assets"), list):
        return ['the report needs an "assets" list']
    problems: list[str] = []
    seen_ids: set[str] = set()
    repeated_ids: set[str] = set()
    for position, asset in enumerate(report["assets"], start=1):
        asset_id = asset.get("id") if isinstance(asset, dict) else None
        if not isinstance(asset_id, str) or not asset_id:
            problems.append(f"asset #{position} has no id")
            continue
        if asset_id in seen_ids:
            if asset_id not in repeated_ids:
                problems.append(f'asset id "{asset_id}" appears twice')
                repeated_ids.add(asset_id)
            continue
        seen_ids.add(asset_id)
        problems.extend(_asset_problems(asset_id, asset, department))
    return problems


def binary_asset_problems(paths: list[str], binary_assets: dict) -> list[str]:
    extensions = set(binary_assets["extensions"])
    allowed_by_route = binary_assets["allowed_by_route"]
    found = [path for path in paths if Path(path).suffix.lower() in extensions]
    problems = [
        f"{path} is a binary asset git would commit, but no allowed route permits one ({allowed_by_route})"
        for path in found[:BINARY_ASSETS_SHOWN]
    ]
    if len(found) > BINARY_ASSETS_SHOWN:
        problems.append(f"and {len(found) - BINARY_ASSETS_SHOWN} more")
    return problems


def _git_bytes(root: Path, *arguments: str) -> bytes:
    return subprocess.run(["git", *arguments], cwd=root, capture_output=True, check=True).stdout


def _fingerprint(path: Path) -> str:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return "missing"
    if stat.S_ISLNK(info.st_mode):
        return "120000 " + hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
    if stat.S_ISDIR(info.st_mode):
        return "directory"
    mode = "100755" if info.st_mode & stat.S_IXUSR else "100644"
    return mode + " " + hashlib.sha256(path.read_bytes()).hexdigest()


def tree_snapshot(root: Path) -> dict:
    output = _git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = output.split(b"\0")
    entries = {}
    index = 0
    while index < len(fields) and fields[index]:
        field = fields[index]
        status = field[:2].decode("ascii")
        paths = [os.fsdecode(field[3:])]
        index += 1
        if "R" in status or "C" in status:
            paths.append(os.fsdecode(fields[index]))
            index += 1
        fingerprints = tuple(_fingerprint(root / path) for path in paths)
        entries[tuple(paths)] = (status, fingerprints)
    return entries


def first_changed_path(before: dict, after: dict) -> str | None:
    for paths, entry in after.items():
        if before.get(paths) != entry:
            return paths[0]
    for paths in before:
        if paths not in after:
            return paths[0]
    return None


def committable_paths(root: Path) -> list[str]:
    output = _git_bytes(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    paths = dict.fromkeys(os.fsdecode(path) for path in output.split(b"\0") if path)
    return [path for path in paths if os.path.lexists(root / path)]


def _read_report(stdout: str, department: Department) -> tuple[list[str], int]:
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as error:
        began = stdout[:OUTPUT_QUOTED_CHARACTERS]
        return [f"the report is not valid JSON: {error}; output began: {began}"], 0
    problems = report_problems(report, department)
    if problems:
        return problems, 0
    return [], len(report["assets"])


def check_department(department: Department, root: Path) -> DepartmentResult:
    before = tree_snapshot(root)
    completed = subprocess.run(
        department.asset_command,
        shell=True,
        cwd=root,
        stdout=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    after = tree_snapshot(root)
    problems: list[str] = []
    asset_count = 0
    if completed.returncode != 0:
        problems.append(f"asset command exited {completed.returncode}: {department.asset_command}")
    changed_path = first_changed_path(before, after)
    if changed_path is not None:
        problems.append(f"the asset command changed {changed_path}; it must leave the working tree unchanged")
    if completed.returncode == 0:
        report_found, asset_count = _read_report(completed.stdout, department)
        problems.extend(report_found)
    binary_assets = department.contract["binary_assets"]
    if binary_assets["allowed_by_route"] not in department.routes:
        problems.extend(binary_asset_problems(committable_paths(root), binary_assets))
    return DepartmentResult(problems, completed.stdout, asset_count)


def save_result(git_dir: Path, department: Department, result: DepartmentResult) -> Path:
    folder = git_dir / "studio" / "pack-reports"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{department.pack['name']}-{department.name}.json"
    saved = {"problems": result.problems, "stdout": result.stdout}
    path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
    return path


def _git_path(directory: Path, flag: str) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", flag], cwd=directory, capture_output=True, text=True
        )
    except OSError:
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    return Path(completed.stdout.strip())


def _shown_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _passing_line(asset_count: int) -> str:
    if asset_count == 0:
        return "0 assets"
    return f"{asset_count} assets within budget"


def check_packs(config: Path | None = None, cwd: Path | None = None) -> int:
    start = Path.cwd() if cwd is None else Path(cwd)
    root = _git_path(start, "--show-toplevel")
    git_dir = _git_path(start, "--absolute-git-dir")
    if root is None or git_dir is None:
        print(f"check-packs: {start} is not inside a git work tree, so nothing was checked.", file=sys.stderr)
        return 2
    root = root.resolve()
    if config is None:
        config_path = project_config_root(root) / ".studio" / "implementation_loop.toml"
        if not config_path.is_file():
            print(f"check-packs: no {config_path}, so no pack is declared.")
            return 0
    else:
        config_path = Path(config)
        if not config_path.is_file():
            print(f"check-packs: no config file at {config_path}, so nothing was checked.", file=sys.stderr)
            return 2
    try:
        departments = load_declaration(config_path)
    except PackConfigError as error:
        print(f"check-packs: {error}", file=sys.stderr)
        return 2
    if not departments:
        print(f"check-packs: {config_path} declares no pack.")
        return 0
    failed = False
    for department in departments:
        result = check_department(department, root)
        save_result(git_dir, department, result)
        if not result.problems:
            print(f"{department.label}: {_passing_line(result.asset_count)}")
            continue
        failed = True
        for problem in result.problems:
            print(f"{department.label}: {problem}")
        print(f"See {_shown_path(pack_doc_path(department.pack), root)}")
    return 1 if failed else 0

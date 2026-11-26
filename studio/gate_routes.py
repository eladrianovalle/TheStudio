from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

RUN_RECORD_PREFIXES = (".studio/output/impl_loop/", "reviewer-concerns/")
SUITE_KEYS = ("command", "paths")
GLOB_CHARACTERS = ("*", "?", "[")


class SuiteError(ValueError):
    def __init__(self, message: str, fix: str):
        super().__init__(message)
        self.fix = fix


class RoutesError(RuntimeError):
    pass


def _refusal(section: str, source: Path | str, reason: str, fix: str) -> SuiteError:
    return SuiteError(f"bad-suite: [{section}] in {source} {reason}.", fix)


def _path_shape_reason(path: str) -> str | None:
    segments = path.split("/")
    if (
        not path.strip()
        or path.startswith("/")
        or path.startswith("./")
        or "\\" in path
        or ".." in segments
        or "." in segments
        or "" in segments[:-1]
    ):
        return f'path "{path}" must be repo-relative'
    if any(character in path for character in GLOB_CHARACTERS):
        return f'path "{path}" has a glob character'
    return None


def _path_existence_reason(path: str, root: Path) -> str | None:
    target = root / path
    if path.endswith("/"):
        if target.is_dir():
            return None
        return f'path "{path}" does not exist as written'
    if target.is_file():
        return None
    if target.is_dir():
        return f'path "{path}" does not exist as written, write "{path}/"'
    return f'path "{path}" does not exist as written'


def _is_list_of_text(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    return all(isinstance(entry, str) for entry in value)


def check_suites(table: object, root: Path | None, source: Path | str) -> dict:
    if not isinstance(table, dict):
        raise _refusal(
            "gate.suites", source, "gate.suites is not a table",
            f"write each suite as its own table in {source}, such as [gate.suites.web] with a command and paths.",
        )
    suites = {}
    for name, suite in table.items():
        section = f"gate.suites.{name}"
        if not isinstance(suite, dict):
            raise _refusal(
                section, source, "is not a table",
                f"write [{section}] in {source} as a table holding a command and paths.",
            )
        for key in suite:
            if key not in SUITE_KEYS:
                raise _refusal(
                    section, source, f'has unknown key "{key}"; a suite takes only command and paths',
                    f'remove "{key}" from [{section}] in {source}, or rename it to command or paths.',
                )
        command = suite.get("command")
        if not isinstance(command, str) or not command.strip():
            raise _refusal(
                section, source, "has no command, or it is blank or not text",
                f'give [{section}] in {source} a command, such as command = "npm test".',
            )
        paths = suite.get("paths")
        if not _is_list_of_text(paths):
            raise _refusal(
                section, source, "has no paths, or it is empty or not a list of text",
                f'give [{section}] in {source} a list of the folders and files it covers, such as paths = ["web/"].',
            )
        for path in paths:
            reason = _path_shape_reason(path)
            if reason is None and root is not None:
                reason = _path_existence_reason(path, root)
            if reason is not None:
                raise _refusal(
                    section, source, reason,
                    f"write each path in [{section}] in {source} relative to the repository root, "
                    "with no glob, ending a folder with /, naming a folder or file that exists.",
                )
        suites[name] = {"command": command, "paths": list(paths)}
    return suites


def _git_paths(root: Path, *arguments: str) -> list[str]:
    completed = subprocess.run(["git", *arguments], cwd=str(root), capture_output=True)
    if completed.returncode != 0:
        why = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RoutesError(f"`git {' '.join(arguments)}` failed in {root}: {why}")
    listing = completed.stdout.decode("utf-8", errors="surrogateescape")
    return [path for path in listing.split("\0") if path]


def _every_changed_file(root: Path, base_sha: str) -> list[str]:
    differing = _git_paths(root, "diff", "--name-only", "--no-renames", "-z", base_sha, "--")
    untracked = _git_paths(root, "ls-files", "--others", "--exclude-standard", "-z")
    return sorted(set(differing) | set(untracked))


def changed_files(root: Path, base_sha: str) -> list[str]:
    every = _every_changed_file(root, base_sha)
    return [path for path in every if not path.startswith(RUN_RECORD_PREFIXES)]


def file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_changed(root: Path, base_sha: str, gate_config: str | None, gate_config_sha256: str | None = None) -> bool:
    if gate_config is None:
        return False
    if gate_config in _every_changed_file(root, base_sha):
        return True
    if gate_config_sha256 is None:
        return False
    return file_digest(root / gate_config) != gate_config_sha256


def _covers(suite_path: str, changed_path: str) -> bool:
    if suite_path.endswith("/"):
        return changed_path.startswith(suite_path)
    return changed_path == suite_path


def route(suites: dict, default: str, changed: list[str]) -> tuple[list[dict], list[str]]:
    routes = []
    claimed = set()
    for name, suite in suites.items():
        covered = [path for path in changed if any(_covers(suite_path, path) for suite_path in suite["paths"])]
        if covered:
            routes.append({"suite": name, "command": suite["command"]})
            claimed.update(covered)
    unclaimed = [path for path in changed if path not in claimed]
    if unclaimed or not changed:
        routes.append({"suite": None, "command": default})
    return routes, unclaimed


def run(root: Path, routes: list[dict]) -> list[dict]:
    results = []
    for gate in routes:
        completed = subprocess.run(
            gate["command"], shell=True, cwd=str(root), stdout=sys.stderr, stderr=sys.stderr,
        )
        results.append({"suite": gate["suite"], "command": gate["command"], "exit_code": completed.returncode})
    return results


GATE_KEYS = {"test_command", "suites", "gate_config"}


def _read_gate(text: str) -> dict:
    try:
        gate = json.loads(text)
    except json.JSONDecodeError as error:
        raise RoutesError(f"the --gate input is not JSON: {error}") from error
    if not isinstance(gate, dict) or set(gate) != GATE_KEYS:
        raise RoutesError("the --gate input must be an object holding exactly test_command, suites and gate_config")
    test_command = gate["test_command"]
    if not isinstance(test_command, str) or not test_command.strip():
        raise RoutesError("the --gate input's test_command is blank or not text")
    gate_config = gate["gate_config"]
    if not (gate_config is None or isinstance(gate_config, str)):
        raise RoutesError("the --gate input's gate_config is neither text nor null")
    try:
        suites = check_suites(gate["suites"], None, "the --gate input")
    except SuiteError as error:
        raise RoutesError(str(error)) from error
    return {"test_command": test_command, "suites": suites, "gate_config": gate_config}


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gate_routes.py",
        description="Run the gate suites that cover the files changed since a base commit.",
    )
    parser.add_argument("--base", required=True, help="the commit the unit started from")
    parser.add_argument("--gate", required=True, choices=["-"], help="read the gate as JSON on stdin")
    options = parser.parse_args(arguments)
    root = Path.cwd()
    try:
        gate = _read_gate(sys.stdin.read())
        changed = changed_files(root, options.base)
        edited = config_changed(root, options.base, gate["gate_config"])
    except RoutesError as error:
        print(f"gate_routes: {error}", file=sys.stderr)
        return 2
    routes, unclaimed = route(gate["suites"], gate["test_command"], changed)
    runs = run(root, routes)
    print(json.dumps({"runs": runs, "unclaimed": unclaimed, "config_changed": edited}))
    if all(entry["exit_code"] == 0 for entry in runs):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

"""Resolve one portable Forge unit before starting its Node orchestration host."""
import json
from pathlib import Path
import re
import shutil
import subprocess

from impl_loop import load_loop_config, project_config_root, runtime_knobs, validate_work_dir
from stats import build_plan_section, parse_build_plan, parse_frontmatter, UNIT_OPENER


def add_parser(subparsers):
    parser = subparsers.add_parser("forge", help="Build and grade one implementation unit.")
    parser.add_argument("title", nargs="*")
    parser.add_argument("--spec")
    parser.add_argument("--unit")
    parser.add_argument("--allow-draft", action="store_true")
    parser.add_argument("--branch")
    parser.add_argument("--work-dir")
    parser.add_argument("--test")
    parser.add_argument("--runtime", choices=["codex", "claude"], default="codex")
    for role in ("writer", "editor"):
        parser.add_argument(f"--{role}-runtime", choices=["codex", "claude"])
        parser.add_argument(f"--{role}-model")
    parser.add_argument("--plan", action="store_true")


def resolve_unit(args, cwd):
    title = " ".join(args.title)
    if not args.spec:
        if not title:
            raise ValueError("Supply a unit title or --spec")
        return {"unit_id": args.unit or re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_"),
                "title": title, "acceptance_criteria": [], "instructions": title}

    path = cwd / args.spec
    if not path.is_file() and "/" not in args.spec and not args.spec.endswith(".md"):
        specs = ".studio/specs" if (cwd / ".studio/source").is_dir() else "specs"
        path = cwd / specs / (args.spec + ".md")
    units = []

    def refusal(reason):
        found = ", ".join(u.unit_id for u in units) or "none"
        return ValueError(f"{reason} at {path}. Units found: {found}. Add criteria or run "
                          "without --spec and provide a title.")

    if not path.is_file():
        raise refusal("missing file")
    spec = path.read_text()
    section = build_plan_section(spec)
    if section is None:
        raise refusal("no Build Plan")
    units = parse_build_plan(spec, path.stem, str(path))
    matches = [u for u in units if not args.unit or u.unit_id == args.unit]
    if len(matches) != 1:
        raise refusal("ambiguous unit" if matches else "unknown unit")
    unit = matches[0]
    entry = next(m for m in UNIT_OPENER.finditer(section) if m[1] == unit.unit_id)
    following = section[entry.end():]
    following = re.split(r"(?m)^ {0,3}#{1,3}\s|" + UNIT_OPENER.pattern, following, maxsplit=1)[0]
    criteria = re.findall(r"(?m)^\s*[-*]\s+\[[ xX]\]\s+(.+)$", following)
    if not criteria:
        raise refusal("empty criteria list")
    status = parse_frontmatter(spec).get("status", "unknown")
    if status != "approved" and not args.allow_draft:
        raise ValueError(f"{path} has status {status}; acknowledge with --allow-draft")
    return {"unit_id": unit.unit_id, "title": unit.title, "acceptance_criteria": criteria,
            "spec": str(path), "instructions": f"Implement only {unit.unit_id} in {path}. {title}".strip()}


def run(args):
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    cwd = validate_work_dir(args.work_dir or root, root)
    if Path(subprocess.check_output(["git", "-C", cwd, "rev-parse", "--show-toplevel"], text=True).strip()) != cwd:
        raise ValueError("--work-dir must name the worktree root")
    unit = resolve_unit(args, cwd)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_]*", unit["unit_id"]):
        raise ValueError("Expected an alphanumeric snake_case unit id")
    config = project_config_root(cwd) / ".studio/implementation_loop.toml"
    knobs = runtime_knobs(load_loop_config(config))
    if args.test:
        knobs["test_command"] = args.test
    # The portable CLI has no predicted paths. Apply tokenized checks after files are known.
    branch = subprocess.check_output(["git", "-C", cwd, "branch", "--show-current"], text=True).strip()
    if not branch:
        raise ValueError("Detached HEAD; check out a feature branch first")
    target = args.branch or (f"impl/{unit['unit_id']}" if branch in ("main", "master") else branch)
    if target in ("main", "master") or subprocess.run(
            ["git", "check-ref-format", "--branch", target], capture_output=True).returncode:
        raise ValueError(f"Invalid or protected branch: {target}")
    plan = {**knobs, **unit, "branch": target, "starting_branch": branch, "work_dir": str(cwd),
            "base_sha": subprocess.check_output(["git", "-C", cwd, "rev-parse", "HEAD"], text=True).strip(),
            "roles": {role: {"runtime": getattr(args, f"{role}_runtime") or args.runtime,
                             "model": getattr(args, f"{role}_model")} for role in ("writer", "editor")}}
    if args.plan:
        print(json.dumps(plan, indent=2))
        return
    node = shutil.which("node")
    if not node:
        raise ValueError("Forge host requires Node.js")
    host = Path(__file__).with_name("forge_host.mjs")
    result = subprocess.run([node, host], input=json.dumps(plan), text=True, cwd=cwd)
    raise SystemExit(result.returncode)

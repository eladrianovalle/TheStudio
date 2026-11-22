#!/usr/bin/env python3
"""Build the trees the /forge editor is measured on.

A case file is a recipe: a past unit's `writer:` commit, the criteria it was graded
against, and optionally a later tree or a patch to put on top. `build` turns each recipe
into a small standalone git repository that holds nothing later than that commit, proves
the case is what it claims, and writes the writer handoff a real editor would find there.
The design, and why each step exists, is the section "A case" in specs/judged-rules.md.

    python studio/editor_measure.py build [--root <dir>]

Exit codes: 0 when every case built and proved, 1 when a case was refused, 2 when a
case's commits are missing from this clone or the arguments are bad.

This module measures Studio's own editor against Studio's own history, so it does not
ship to installed repositories (it is not in install.SOURCE_FILES).
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from impl_loop import explain_unquotable_path

STUDIO_ROOT = Path(__file__).resolve().parent
REPO_ROOT = STUDIO_ROOT.parent
CASES_DIR = STUDIO_ROOT / "evals" / "forge_editor" / "cases"
PATCHES_DIR = STUDIO_ROOT / "evals" / "forge_editor" / "patches"

# Outside the repository on purpose: the editor sees the path it works in, and a tree under
# studio/evals/ would say what it is before the editor read a line.
DEFAULT_ROOT = "~/.studio/checkouts"

# Words that would tell the editor its tree is a case. A root or tree name holding any of
# them, in any case and anywhere in the name, is refused.
TELLTALE_WORDS = (
    "eval", "case", "plant", "defect", "clean", "test", "fixture", "judge", "measure", "probe",
)

REQUIRED_FIELDS = (
    "unit_id", "kind", "source", "writer_sha", "spec_file", "acceptance_criteria", "test_command",
)
KINDS = ("defect", "clean")
SOURCES = ("review_fix", "plant", "as_built")


class CaseRefused(Exception):
    """A case is not what it claims, or cannot be built as written. Exit code 1."""


class HistoryMissing(Exception):
    """A commit a case names is not in this clone. Exit code 2."""


# --- running git and commands ----------------------------------------------


def _git(directory: Path, *arguments: str, env: dict | None = None) -> str:
    """Run `git -C <directory> <arguments>` and return what it printed, stripped.

    Raises subprocess.CalledProcessError when git refuses; the build turns that into a
    refusal naming the case.
    """
    result = subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return result.stdout.strip()


def _git_succeeds(directory: Path, *arguments: str) -> bool:
    """True when `git -C <directory> <arguments>` exits 0. For git's yes/no questions."""
    result = subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _run_shell(command: str, directory: Path) -> subprocess.CompletedProcess:
    """Run a case's own command (its test command or probe) in the built tree."""
    return subprocess.run(command, shell=True, cwd=directory, capture_output=True, text=True)


def _output_tail(result: subprocess.CompletedProcess, lines: int = 15) -> str:
    """The last few lines a command printed, so a refusal shows why it failed."""
    printed = (result.stdout + result.stderr).strip().splitlines()
    return "\n".join("    " + line for line in printed[-lines:])


# --- where a tree may go ----------------------------------------------------


def telltale_word_in(text: str) -> str | None:
    """The first telltale word ``text`` holds, ignoring letter case, or None."""
    lowered = text.lower()
    for word in TELLTALE_WORDS:
        if word in lowered:
            return word
    return None


def explain_bad_location(text: str, what: str) -> str | None:
    """Say why ``text`` (a root path or a tree name) cannot be used, or None if it can.

    A tree's path reaches the editor's prompt and the editor's eyes: a telltale word tells
    it this is a case, and a character explain_unquotable_path refuses could change what
    the editor's git commands run.
    """
    word = telltale_word_in(text)
    if word is not None:
        return f"{what} {text!r} holds the word {word!r}, which would tell the editor it is looking at a case"
    unquotable = explain_unquotable_path(text)
    if unquotable is not None:
        return f"{what} {text!r} cannot be used:\n{unquotable}"
    return None


# --- reading a case ---------------------------------------------------------


def load_case(case_path: Path) -> dict:
    """Read one case file and refuse it when a field the build relies on is missing or unknown."""
    name = case_path.stem
    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CaseRefused(f"case {name}: {case_path} is not valid JSON ({error})") from error

    missing = [field for field in REQUIRED_FIELDS if field not in case]
    if missing:
        raise CaseRefused(f"case {name}: missing required field(s) {', '.join(missing)}")
    if case["kind"] not in KINDS:
        raise CaseRefused(f"case {name}: kind {case['kind']!r} is not one of {', '.join(KINDS)}")
    if case["source"] not in SOURCES:
        raise CaseRefused(f"case {name}: source {case['source']!r} is not one of {', '.join(SOURCES)}")
    if not case["acceptance_criteria"]:
        raise CaseRefused(f"case {name}: acceptance_criteria is empty")
    if case["kind"] == "defect" and not case.get("probe"):
        raise CaseRefused(f"case {name}: a defect case needs a probe that shows the defect")
    return case


def commits_named_by(case: dict) -> list[str]:
    """Every commit the case needs from this clone: writer, tree_sha and the probe's source."""
    commits = [case["writer_sha"]]
    if case.get("tree_sha"):
        commits.append(case["tree_sha"])
    if case.get("probe"):
        commits.append(case["probe"]["from_sha"])
    return commits


def require_history(source_repo: Path, name: str, case: dict) -> None:
    """Raise HistoryMissing when a commit the case names is not in ``source_repo``.

    A shallow clone, or one that never fetched the branch a unit was built on, cannot
    build the case at all, which is different from the case being wrong.
    """
    for commit in commits_named_by(case):
        if not _git_succeeds(source_repo, "cat-file", "-e", f"{commit}^{{commit}}"):
            raise HistoryMissing(
                f"case {name}: commit {commit} is not in {source_repo}. The history is missing "
                "from this clone; fetch the full history (`git fetch --unshallow`, or the branch "
                "the unit was built on) and build again."
            )


# --- building a tree --------------------------------------------------------


def start_tree(tree: Path, case: dict, source_repo: Path) -> None:
    """Make a fresh repository at ``tree`` holding the writer commit on the unit's branch.

    A tree left by an earlier build is removed first. Fetching a commit by its id brings
    only that commit and its ancestors, so nothing later than it arrives except tree_sha,
    which strip_history removes once its tree has been taken.
    """
    if tree.exists():
        shutil.rmtree(tree)
    tree.parent.mkdir(parents=True, exist_ok=True)

    branch = f"impl/{case['unit_id']}"
    commits = [case["writer_sha"]]
    if case.get("tree_sha"):
        commits.append(case["tree_sha"])

    _git(tree.parent, "init", "--quiet", f"--initial-branch={branch}", tree.name)
    _git(tree, "fetch", "--quiet", "--no-tags", str(source_repo), *commits)
    _git(tree, "checkout", "--quiet", "-B", branch, case["writer_sha"])


def refuse_mixed_range(tree: Path, name: str, case: dict) -> None:
    """Refuse a tree_sha whose history since the writer commit holds someone else's work.

    The tree_sha tree is meant to be the writer's unit plus its own review. A merge
    commit, or another unit's `writer:` commit, between the two would put a second
    unit's code in front of the editor as if this unit wrote it.
    """
    writer_sha = case["writer_sha"]
    tree_sha = case["tree_sha"]
    if not _git_succeeds(tree, "merge-base", "--is-ancestor", writer_sha, tree_sha):
        raise CaseRefused(f"case {name}: tree_sha {tree_sha} does not descend from writer_sha {writer_sha}")

    merges = _git(tree, "rev-list", "--merges", f"{writer_sha}..{tree_sha}").splitlines()
    if merges:
        raise CaseRefused(
            f"case {name}: merge commit {merges[0]} lies between writer_sha {writer_sha} and tree_sha {tree_sha}"
        )

    for line in _git(tree, "log", "--format=%H %s", f"{writer_sha}..{tree_sha}").splitlines():
        commit, _, subject = line.partition(" ")
        if not subject.startswith("writer:"):
            continue
        named_unit = subject[len("writer:"):].strip().split(" ")[0]
        if named_unit != case["unit_id"]:
            raise CaseRefused(
                f"case {name}: commit {commit} ({subject!r}) is another unit's writer commit, "
                f"and it lies between writer_sha {writer_sha} and tree_sha {tree_sha}"
            )


def files_in_patch(tree: Path, patch_path: Path) -> set[str]:
    """The paths a patch changes, as git apply reads them."""
    numstat = _git(tree, "apply", "--numstat", str(patch_path))
    return {line.split("\t")[2] for line in numstat.splitlines()}


def apply_patch(tree: Path, name: str, case: dict, patches_dir: Path) -> None:
    """Apply the case's patch to the index and working tree, or refuse the case.

    A plant's patch may only touch files in the unit's own diff, because that diff is
    what the editor is told to read; a defect planted elsewhere is one it was never
    asked to look at.
    """
    patch_path = patches_dir / case["patch"]
    if not patch_path.is_file():
        raise CaseRefused(f"case {name}: patch {case['patch']} is not in {patches_dir}")
    if not _git_succeeds(tree, "apply", "--check", "--index", str(patch_path)):
        raise CaseRefused(f"case {name}: patch {case['patch']} does not apply to the tree")

    if case["source"] == "plant":
        writer_sha = case["writer_sha"]
        unit_files = set(_git(tree, "diff", "--name-only", f"{writer_sha}^", writer_sha).splitlines())
        outside = sorted(files_in_patch(tree, patch_path) - unit_files)
        if outside:
            raise CaseRefused(
                f"case {name}: plant patch {case['patch']} touches {', '.join(outside)}, "
                "outside the unit's own diff"
            )

    _git(tree, "apply", "--index", str(patch_path))


def amend_keeping_identity(tree: Path, writer_sha: str) -> None:
    """Amend HEAD with the staged changes, keeping the writer commit's message and identity.

    Author, committer and both dates are copied from the real commit, so the amended
    commit looks like the one the writer made and two builds give the same commit id.
    """
    identity = _git(
        tree, "show", "--no-patch", "--date=raw",
        "--format=%an%x00%ae%x00%ad%x00%cn%x00%ce%x00%cd", writer_sha,
    )
    author_name, author_email, author_date, committer_name, committer_email, committer_date = identity.split("\x00")
    environment = dict(os.environ)
    environment["GIT_AUTHOR_NAME"] = author_name
    environment["GIT_AUTHOR_EMAIL"] = author_email
    environment["GIT_AUTHOR_DATE"] = author_date
    environment["GIT_COMMITTER_NAME"] = committer_name
    environment["GIT_COMMITTER_EMAIL"] = committer_email
    environment["GIT_COMMITTER_DATE"] = committer_date
    _git(
        tree, "commit", "--amend", "--quiet", "--no-edit", "--cleanup=verbatim",
        "--no-verify", "--no-gpg-sign",
        env=environment,
    )


def shape_tree(tree: Path, name: str, case: dict, patches_dir: Path) -> None:
    """Turn the writer commit into the case's tree: later tree, patch, no previous review.

    The reviewer-concerns file is the historic editor's notes on this very unit; leaving
    it would hand the editor its predecessor's answer.
    """
    if case.get("tree_sha"):
        refuse_mixed_range(tree, name, case)
        _git(tree, "read-tree", "--reset", "-u", case["tree_sha"])
    if case.get("patch"):
        apply_patch(tree, name, case, patches_dir)
    # --force: after read-tree the file is staged but not committed, and git rm would refuse it.
    _git(tree, "rm", "--quiet", "--force", "--ignore-unmatch", "--", f"reviewer-concerns/{case['unit_id']}.md")

    nothing_changed = _git_succeeds(tree, "diff", "--cached", "--quiet", "HEAD")
    if not nothing_changed:
        amend_keeping_identity(tree, case["writer_sha"])


def strip_history(tree: Path) -> None:
    """Remove every trace of what was fetched beyond the tree's own commit and ancestors.

    FETCH_HEAD and the reflog still point at tree_sha and at the commit an amend
    replaced; with them gone, pruning drops those objects for good.
    """
    (tree / ".git" / "FETCH_HEAD").unlink(missing_ok=True)
    shutil.rmtree(tree / ".git" / "logs", ignore_errors=True)
    _git(tree, "gc", "--quiet", "--prune=now")


# --- proving a case ---------------------------------------------------------


def restore_tree(tree: Path) -> None:
    """Put the tree back to its commit after a proof step, leaving no file behind.

    The reset runs with reflogs off: strip_history deleted them, and a reset would
    otherwise start a new one.
    """
    _git(tree, "-c", "core.logAllRefUpdates=false", "reset", "--quiet", "--hard")
    _git(tree, "clean", "--quiet", "--force", "-d", "-x")


def collapse_whitespace(text: str) -> str:
    """``text`` with every run of whitespace turned into one space, so line wrapping is ignored."""
    return " ".join(text.split())


def prove_criteria(tree: Path, name: str, case: dict) -> None:
    """Refuse the case unless every criterion appears in its spec file as the tree has it."""
    spec_path = tree / case["spec_file"]
    if not spec_path.is_file():
        raise CaseRefused(f"case {name}: spec_file {case['spec_file']} is not in the built tree")
    spec_text = collapse_whitespace(spec_path.read_text(encoding="utf-8"))
    for number, criterion in enumerate(case["acceptance_criteria"], start=1):
        if collapse_whitespace(criterion) not in spec_text:
            raise CaseRefused(
                f"case {name}: criterion {number} is not in {case['spec_file']} as it stands "
                f"in the built tree: {criterion!r}"
            )


def prove_test_command(tree: Path, name: str, case: dict) -> dict:
    """Run the case's test command in the tree; refuse unless it exits 0.

    Returns the handoff's `tests` record of that run.
    """
    command = case["test_command"]
    result = _run_shell(command, tree)
    restore_tree(tree)
    if result.returncode != 0:
        raise CaseRefused(
            f"case {name}: its test command `{command}` exits {result.returncode} in the built tree:\n"
            f"{_output_tail(result)}"
        )
    return {"command": command, "passed": True, "exit_code": 0}


def place_probe_files(tree: Path, source_repo: Path, name: str, probe: dict) -> None:
    """Copy the probe's files into the tree from the commit it names, read from this clone.

    They are read here rather than fetched into the tree, so the tree never holds an
    object from that (usually later) commit.
    """
    for relative_path in probe["paths"]:
        result = subprocess.run(
            ["git", "-C", str(source_repo), "show", f"{probe['from_sha']}:{relative_path}"],
            capture_output=True,
        )
        if result.returncode != 0:
            raise CaseRefused(f"case {name}: probe path {relative_path} is not in commit {probe['from_sha']}")
        destination = tree / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(result.stdout)


def prove_probe(tree: Path, source_repo: Path, name: str, case: dict) -> None:
    """Run the probe: it must fail on a defect case and pass on a clean one.

    A probe exits 0 only when the defect is absent, so a defect case whose probe passes
    holds no defect, and a clean case whose probe fails is not clean.
    """
    probe = case.get("probe")
    if not probe:
        return
    place_probe_files(tree, source_repo, name, probe)
    result = _run_shell(probe["command"], tree)
    restore_tree(tree)
    if case["kind"] == "defect" and result.returncode == 0:
        raise CaseRefused(
            f"case {name}: the defect case's probe `{probe['command']}` passes, so the tree does not hold the defect"
        )
    if case["kind"] == "clean" and result.returncode != 0:
        raise CaseRefused(
            f"case {name}: the clean case's probe `{probe['command']}` fails (exit {result.returncode}):\n"
            f"{_output_tail(result)}"
        )


# --- the writer handoff -----------------------------------------------------


def handoff_path(tree: Path, unit_id: str) -> Path:
    """Where the loop keeps a unit's writer handoff, relative to the tree it built in."""
    return tree / ".studio" / "output" / "impl_loop" / unit_id / f"impl--{unit_id}--writer.json"


def write_writer_handoff(tree: Path, case: dict, tests: dict) -> Path:
    """Write the writer handoff a real editor finds next to the unit it reviews.

    The shape is the WRITER_HANDOFF schema in .claude/workflows/implementation-loop.js.
    The commit ids and files come from the built tree, not the case file, so an amended
    commit is reported as the commit the editor actually sees. `load_bearing` is empty:
    the historic writer's items are not in public history, and a real editor may not edit
    a load-bearing item, so carrying any would change what the editor is allowed to do.
    """
    unit_id = case["unit_id"]
    handoff = {
        "unit_id": unit_id,
        "base_sha": _git(tree, "rev-parse", "--short", "HEAD^"),
        "writer_sha": _git(tree, "rev-parse", "--short", "HEAD"),
        "files_touched": _git(tree, "diff", "--name-only", "HEAD^", "HEAD").splitlines(),
        "tests": tests,
        # A writer hands over a unit it says is done; the editor's verdict is what is measured.
        "mvi_claimed": True,
        "mutation_check": {"performed": False, "reason": "not_configured"},
        "load_bearing": [],
        "stage": "writer",
    }
    path = handoff_path(tree, unit_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(handoff, indent=2) + "\n", encoding="utf-8")
    return path


# --- the build command ------------------------------------------------------


def build_case(case_path: Path, root: Path, patches_dir: Path, source_repo: Path) -> Path:
    """Build, prove and hand off one case. Returns the tree; raises CaseRefused or HistoryMissing."""
    name = case_path.stem
    problem = explain_bad_location(name, "tree name")
    if problem is not None:
        raise CaseRefused(f"case {name}: {problem}")

    case = load_case(case_path)
    require_history(source_repo, name, case)

    tree = root / name
    try:
        start_tree(tree, case, source_repo)
        shape_tree(tree, name, case, patches_dir)
        strip_history(tree)
        prove_criteria(tree, name, case)
        tests = prove_test_command(tree, name, case)
        prove_probe(tree, source_repo, name, case)
    except subprocess.CalledProcessError as error:
        command = " ".join(shlex.quote(part) for part in error.cmd)
        raise CaseRefused(f"case {name}: `{command}` failed:\n{(error.stderr or '').strip()}") from error
    write_writer_handoff(tree, case, tests)
    return tree


def build(root: Path, cases_dir: Path, patches_dir: Path, source_repo: Path) -> int:
    """Build every case under ``cases_dir`` into ``root``, stopping at the first that fails.

    Returns the exit code: 0 all built and proved, 1 a case refused, 2 history missing
    or a bad root.
    """
    problem = explain_bad_location(str(root), "root")
    if problem is not None:
        print(f"editor_measure build: {problem}", file=sys.stderr)
        return 2

    case_paths = sorted(cases_dir.glob("*.json"))
    if not case_paths:
        print(f"editor_measure build: no case files in {cases_dir}; nothing to build")
        return 0

    for case_path in case_paths:
        try:
            tree = build_case(case_path, root, patches_dir, source_repo)
        except HistoryMissing as error:
            print(f"editor_measure build: {error}", file=sys.stderr)
            return 2
        except CaseRefused as error:
            print(f"editor_measure build: refused {error}", file=sys.stderr)
            return 1
        head = _git(tree, "rev-parse", "--short", "HEAD")
        print(f"built {case_path.stem} at {tree} (head {head})")

    print(f"editor_measure build: {len(case_paths)} case(s) built and proved under {root}")
    return 0


def main(
    argv: list[str] | None = None,
    cases_dir: Path = CASES_DIR,
    patches_dir: Path = PATCHES_DIR,
    source_repo: Path = REPO_ROOT,
) -> int:
    """Parse the command line and run the subcommand. The directories are parameters for tests."""
    parser = argparse.ArgumentParser(
        prog="editor_measure.py",
        description="Build the trees the /forge editor is measured on.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    build_parser = subcommands.add_parser(
        "build", help="turn every case file into a proved tree under the root",
    )
    build_parser.add_argument(
        "--root", default=DEFAULT_ROOT,
        help=f"directory the trees are built in (default {DEFAULT_ROOT})",
    )
    arguments = parser.parse_args(argv)

    root = Path(arguments.root).expanduser().resolve()
    return build(root, cases_dir, patches_dir, source_repo)


if __name__ == "__main__":
    sys.exit(main())

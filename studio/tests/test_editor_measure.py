"""Scenario tests for `editor_measure.py build`: a case file becomes a tree that holds nothing
past its case commit, and a case that is not what it claims is refused by name.

These use a real throwaway git repository rather than mocked subprocess calls. The whole
claim is about what git leaves in a tree (branches, reflogs, objects), and a mock would
only repeat our own assumptions about git back to us.

The fake history is a unit called `greeter` whose writer forgot the "!" its spec asks for:

    base -> writer: greeter -> editor: greeter -> fix greeting -> later
              |\\
              | +-> plant commit                      (source of the plant patches)
              +---> writer: other_unit -> after other (another unit in between)
              +---> side one -+-> merge -> after merge  (a merge in between)
              +---> side two -+
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import editor_measure

STUDIO_DIR = Path(__file__).resolve().parents[1]
PYTHON = shlex.quote(sys.executable)
UNIT = "greeter"

SPEC_TEXT = """# Greeter

**Acceptance criteria:**
- [ ] `greet()` returns a greeting that
      ends with an exclamation mark.
- [ ] The checks script passes.
"""
CRITERIA = [
    "`greet()` returns a greeting that ends with an exclamation mark.",
    "The checks script passes.",
]
CHECKS = "import app\nassert app.greet().startswith('hello')\n"
BANG_PROBE = "import app\nassert app.greet().endswith('!'), app.greet()\n"

WRITER_IDENTITY = {
    "GIT_AUTHOR_NAME": "Writer Agent",
    "GIT_AUTHOR_EMAIL": "writer@example.com",
    "GIT_AUTHOR_DATE": "1700000000 +0100",
    "GIT_COMMITTER_NAME": "Committer Person",
    "GIT_COMMITTER_EMAIL": "committer@example.com",
    "GIT_COMMITTER_DATE": "1700000500 -0500",
}
WRITER_MESSAGE = "writer: greeter\n\nBody line kept as written.\n"


def git(directory: Path, *arguments: str, env: dict | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True, text=True, check=True,
        env={**os.environ, **(env or {})},
    )
    return result.stdout.strip()


def commit_all(repo: Path, message: str, env: dict | None = None) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "--cleanup=verbatim", "-m", message, env=env)
    return git(repo, "rev-parse", "HEAD")


def write(repo: Path, relative_path: str, text: str) -> None:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture(scope="module")
def history(tmp_path_factory):
    """The source repository and the id of every commit in the fake history."""
    repo = tmp_path_factory.mktemp("source")
    git(repo, "init", "--quiet", "--initial-branch=main")
    git(repo, "config", "user.email", "someone@example.com")
    git(repo, "config", "user.name", "Someone")
    git(repo, "config", "commit.gpgsign", "false")
    shas = {}

    write(repo, "specs/greeter.md", SPEC_TEXT)
    write(repo, "app.py", "def greet():\n    return 'hi'\n")
    write(repo, "run_checks.py", "import app\nassert app.greet()\n")
    shas["base"] = commit_all(repo, "base")

    write(repo, "app.py", "def greet():\n    return 'hello'\n")
    write(repo, "run_checks.py", CHECKS)
    shas["writer"] = commit_all(repo, WRITER_MESSAGE, env=WRITER_IDENTITY)

    write(repo, "reviewer-concerns/greeter.md", "# The editor's notes on greeter\n")
    shas["editor"] = commit_all(repo, "editor: greeter")

    write(repo, "app.py", "def greet():\n    return 'hello!'\n")
    write(repo, "probe_bang.py", BANG_PROBE)
    shas["fix"] = commit_all(repo, "fix greeting")

    write(repo, "notes.md", "something later\n")
    shas["later"] = commit_all(repo, "later work")

    git(repo, "checkout", "--quiet", "-b", "plant", shas["writer"])
    write(repo, "app.py", "def greet():\n    return 'hello'  # planted\n")
    write(repo, "run_checks.py", CHECKS + "# planted\n")
    shas["plant"] = commit_all(repo, "plant source")

    git(repo, "checkout", "--quiet", "-b", "other", shas["writer"])
    write(repo, "other.py", "x = 1\n")
    shas["other_writer"] = commit_all(repo, "writer: other_unit")
    write(repo, "app.py", "def greet():\n    return 'hello!'\n")
    shas["after_other"] = commit_all(repo, "fix after another unit")

    git(repo, "checkout", "--quiet", "-b", "side_one", shas["writer"])
    write(repo, "one.txt", "1\n")
    commit_all(repo, "side one")
    git(repo, "checkout", "--quiet", "-b", "side_two", shas["writer"])
    write(repo, "two.txt", "2\n")
    commit_all(repo, "side two")
    git(repo, "checkout", "--quiet", "side_one")
    git(repo, "merge", "--quiet", "--no-edit", "side_two")
    shas["merge"] = git(repo, "rev-parse", "HEAD")
    write(repo, "app.py", "def greet():\n    return 'hello!'\n")
    shas["after_merge"] = commit_all(repo, "fix after a merge")

    git(repo, "checkout", "--quiet", "main")
    return {"repo": repo, **shas}


@pytest.fixture
def checkout_root():
    """A root outside pytest's own temp directory, whose path holds the word 'test' (which the build refuses)."""
    parent = Path(tempfile.mkdtemp(prefix="checkouts-")).resolve()
    yield parent / "trees"
    shutil.rmtree(parent, ignore_errors=True)


@pytest.fixture
def case_dirs(tmp_path):
    """Throwaway cases and patches directories (their paths never reach a tree)."""
    cases = tmp_path / "cases"
    patches = tmp_path / "patches"
    cases.mkdir()
    patches.mkdir()
    return cases, patches


def defect_case(history, **overrides) -> dict:
    """The writer's tree as it was: the "!" is missing, and the fix's probe shows it."""
    case = {
        "unit_id": UNIT,
        "kind": "defect",
        "source": "review_fix",
        "fix_sha": history["fix"],
        "writer_sha": history["writer"],
        "spec_file": "specs/greeter.md",
        "acceptance_criteria": CRITERIA,
        "test_command": f"{PYTHON} run_checks.py",
        "breaks_criterion": 1,
        "defect": "greet() leaves off the exclamation mark.",
        "probe": {"from_sha": history["fix"], "paths": ["probe_bang.py"], "command": f"{PYTHON} probe_bang.py"},
    }
    case.update(overrides)
    return case


def clean_case(history, **overrides) -> dict:
    """The twin, at the fix commit: the probe passes there."""
    case = defect_case(history, kind="clean", tree_sha=history["fix"])
    del case["breaks_criterion"]
    del case["defect"]
    case.update(overrides)
    return case


def write_case(cases_dir: Path, name: str, case: dict) -> None:
    (cases_dir / f"{name}.json").write_text(json.dumps(case, indent=2), encoding="utf-8")


def write_patch(history, patches_dir: Path, name: str, *paths: str, to: str = "plant", from_: str = "writer") -> str:
    diff = git(history["repo"], "diff", history[from_], history[to], "--", *paths)
    (patches_dir / name).write_text(diff + "\n", encoding="utf-8")
    return name


def run_build(history, root, case_dirs, capsys, source_repo=None):
    cases, patches = case_dirs
    code = editor_measure.main(
        ["build", "--root", str(root)],
        cases_dir=cases, patches_dir=patches,
        source_repo=source_repo or history["repo"],
    )
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def commit_identity(repo: Path, commit: str) -> str:
    return git(repo, "show", "--no-patch", "--date=raw", "--format=%B%x00%an%x00%ae%x00%ad%x00%cn%x00%ce%x00%cd", commit)


def assert_holds_nothing_later(tree: Path, history, later: list[str]) -> None:
    assert git(tree, "for-each-ref", "--format=%(refname)") == f"refs/heads/impl/{UNIT}"
    assert git(tree, "branch", "--show-current") == f"impl/{UNIT}"
    assert git(tree, "remote") == ""
    assert not (tree / ".git" / "logs").exists()
    assert not (tree / ".git" / "FETCH_HEAD").exists()
    for name in later:
        assert not editor_measure._git_succeeds(tree, "cat-file", "-e", history[name]), name
    assert not (tree / "reviewer-concerns" / f"{UNIT}.md").exists()


# --- criterion 1: the tree holds the writer commit and nothing past it ------


def test_a_plain_case_builds_a_tree_whose_head_is_the_writer_commit(history, checkout_root, case_dirs, capsys):
    write_case(case_dirs[0], "greeter_one", defect_case(history))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 0, output
    tree = checkout_root / "greeter_one"
    assert git(tree, "rev-parse", "HEAD") == history["writer"]
    assert_holds_nothing_later(tree, history, ["editor", "fix", "later", "plant"])


def test_a_tree_sha_case_keeps_the_writer_identity_and_drops_the_later_commit(history, checkout_root, case_dirs, capsys):
    write_case(case_dirs[0], "greeter_two", clean_case(history))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 0, output
    tree = checkout_root / "greeter_two"
    head = git(tree, "rev-parse", "HEAD")
    assert head != history["writer"]
    assert git(tree, "rev-parse", "HEAD^") == history["base"]
    assert commit_identity(tree, head) == commit_identity(history["repo"], history["writer"])
    assert (tree / "app.py").read_text() == "def greet():\n    return 'hello!'\n"
    # The editor commit added the concerns file; the fix's tree still has it, and the build removes it.
    assert_holds_nothing_later(tree, history, ["editor", "fix", "later"])
    assert not editor_measure._git_succeeds(tree, "cat-file", "-e", history["writer"])


def test_a_patch_case_amends_the_writer_commit_keeping_its_identity(history, checkout_root, case_dirs, capsys):
    cases, patches = case_dirs
    patch = write_patch(history, patches, "fix.patch", "app.py", to="fix")
    write_case(cases, "greeter_three", clean_case(history, tree_sha=None, patch=patch))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 0, output
    tree = checkout_root / "greeter_three"
    head = git(tree, "rev-parse", "HEAD")
    assert head != history["writer"]
    assert commit_identity(tree, head) == commit_identity(history["repo"], history["writer"])
    assert_holds_nothing_later(tree, history, ["editor", "fix", "later"])


# --- criterion 2: the same case gives the same commit, and a rebuild replaces the tree


def test_two_builds_of_a_case_give_the_same_head_and_the_second_replaces_the_first(history, checkout_root, case_dirs, capsys):
    cases, patches = case_dirs
    patch = write_patch(history, patches, "fix.patch", "app.py", to="fix")
    write_case(cases, "greeter_four", clean_case(history, tree_sha=None, patch=patch))

    run_build(history, checkout_root, case_dirs, capsys)
    tree = checkout_root / "greeter_four"
    builds = history["repo"] / "studio/output/editor_measure"
    first_manifest, = builds.glob("*/manifest.json")
    first_runner = first_manifest.with_name("measure-runner.js").read_bytes()
    first_head = git(tree, "rev-parse", "HEAD")
    (tree / "left_by_hand.txt").write_text("from before\n")
    git(tree, "branch", "left_by_hand")

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 0, output
    manifest, = builds.glob("*/manifest.json")
    assert not first_manifest.exists()
    assert manifest.with_name("measure-runner.js").read_bytes() == first_runner
    data = json.loads(manifest.read_text())
    case, = data["cases"]
    assert data["built_at"] and str(tree) in case["prompt"]
    assert case["head"] == first_head
    assert git(tree, "rev-parse", "HEAD") == first_head
    assert not (tree / "left_by_hand.txt").exists()
    assert git(tree, "for-each-ref", "--format=%(refname)") == f"refs/heads/impl/{UNIT}"


# --- criterion 3: the proof refuses a case that is not what it claims -------


def test_build_refuses_a_case_whose_test_command_fails(history, checkout_root, case_dirs, capsys):
    failing = f"{PYTHON} -c \"import app; assert app.greet() == 'bye'\""
    write_case(case_dirs[0], "greeter_five", defect_case(history, test_command=failing))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 1
    assert "case greeter_five" in output
    assert "test command" in output


def test_build_refuses_a_defect_case_whose_probe_passes(history, checkout_root, case_dirs, capsys):
    write_case(case_dirs[0], "greeter_six", defect_case(history, tree_sha=history["fix"]))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 1
    assert "case greeter_six" in output
    assert "probe" in output and "passes" in output


def test_build_refuses_a_clean_case_whose_probe_fails(history, checkout_root, case_dirs, capsys):
    write_case(case_dirs[0], "greeter_seven", clean_case(history, tree_sha=None))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 1
    assert "case greeter_seven" in output
    assert "probe" in output and "fails" in output


def test_build_refuses_a_criterion_the_spec_file_does_not_hold(history, checkout_root, case_dirs, capsys):
    criteria = [CRITERIA[0], "The greeting is in French."]
    write_case(case_dirs[0], "greeter_eight", defect_case(history, acceptance_criteria=criteria))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 1
    assert "case greeter_eight" in output
    assert "criterion 2" in output


# --- criterion 4: a case whose recipe cannot be honoured is refused ---------


def test_build_refuses_a_patch_that_does_not_apply(history, checkout_root, case_dirs, capsys):
    cases, patches = case_dirs
    (patches / "stale.patch").write_text(
        "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n def greet():\n-    return 'nothing like this'\n+    return 'x'\n"
    )
    write_case(cases, "greeter_nine", defect_case(history, source="plant", patch="stale.patch"))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 1
    assert "case greeter_nine" in output
    assert "does not apply" in output


def test_build_refuses_a_plant_that_touches_a_file_outside_the_unit_diff(history, checkout_root, case_dirs, capsys):
    cases, patches = case_dirs
    patch = write_patch(history, patches, "wide.patch", "app.py", "probe_bang.py", to="fix")
    write_case(cases, "greeter_ten", defect_case(history, source="plant", patch=patch))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 1
    assert "case greeter_ten" in output
    assert "probe_bang.py" in output and "outside the unit's own diff" in output


def test_a_plant_inside_the_unit_diff_builds(history, checkout_root, case_dirs, capsys):
    cases, patches = case_dirs
    patch = write_patch(history, patches, "narrow.patch", "app.py", "run_checks.py", from_="fix")
    write_case(cases, "greeter_eleven", defect_case(history, source="plant", patch=patch, tree_sha=history["fix"]))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 0, output
    assert "# planted" in (checkout_root / "greeter_eleven" / "app.py").read_text()
    assert sorted(path.name for path in checkout_root.iterdir()) == ["greeter_eleven"]


def test_build_refuses_a_plant_whose_probe_already_fails_without_the_patch(history, checkout_root, case_dirs, capsys):
    cases, patches = case_dirs
    patch = write_patch(history, patches, "untargeted.patch", "app.py", "run_checks.py")
    write_case(cases, "greeter_weak", defect_case(history, source="plant", patch=patch))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 1
    assert "case greeter_weak" in output
    assert "unplanted control's probe" in output


def test_build_refuses_a_tree_sha_with_another_units_writer_commit_in_between(history, checkout_root, case_dirs, capsys):
    write_case(case_dirs[0], "greeter_twelve", clean_case(history, tree_sha=history["after_other"]))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 1
    assert "case greeter_twelve" in output
    assert "another unit's writer commit" in output
    assert history["other_writer"] in output


def test_build_refuses_a_tree_sha_with_a_merge_commit_in_between(history, checkout_root, case_dirs, capsys):
    write_case(case_dirs[0], "greeter_thirteen", clean_case(history, tree_sha=history["after_merge"]))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 1
    assert "case greeter_thirteen" in output
    assert f"merge commit {history['merge']}" in output


# --- criterion 5: no tell in the location, and missing history exits 2 ------


@pytest.mark.parametrize("word", editor_measure.TELLTALE_WORDS)
def test_build_refuses_a_tree_name_holding_a_telltale_word(word, history, checkout_root, case_dirs, capsys):
    name = f"greeter_{word.upper()}s"
    write_case(case_dirs[0], name, defect_case(history))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 1
    assert f"case {name}" in output
    assert f"'{word}'" in output
    assert not (checkout_root / name).exists()


def test_build_refuses_a_tree_name_with_a_character_it_cannot_quote(history, checkout_root, case_dirs, capsys):
    write_case(case_dirs[0], "greeter&more", defect_case(history))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 1
    assert "case greeter&more" in output
    assert "cannot safely quote" in output


def test_build_refuses_a_root_holding_a_telltale_word(history, checkout_root, case_dirs, capsys):
    write_case(case_dirs[0], "greeter_one", defect_case(history))

    code, output = run_build(history, checkout_root / "evals", case_dirs, capsys)

    assert code == 2
    assert "'eval'" in output
    assert not (checkout_root / "evals").exists()


def test_build_refuses_a_root_with_a_character_it_cannot_quote(history, checkout_root, case_dirs, capsys):
    write_case(case_dirs[0], "greeter_one", defect_case(history))

    code, output = run_build(history, checkout_root / "a+b", case_dirs, capsys)

    assert code == 2
    assert "cannot safely quote" in output


def test_build_exits_2_saying_the_history_is_missing_in_a_clone_without_the_commits(history, checkout_root, case_dirs, capsys, tmp_path):
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "--quiet", "--depth=1", "--branch=main", f"file://{history['repo']}", str(shallow)],
        check=True, capture_output=True,
    )
    write_case(case_dirs[0], "greeter_one", defect_case(history))

    code, output = run_build(history, checkout_root, case_dirs, capsys, source_repo=shallow)

    assert code == 2
    assert "case greeter_one" in output
    assert "history is missing" in output
    assert not (checkout_root / "greeter_one").exists()


# --- criterion 6: the proof leaves nothing, and the handoff is the tree's own


def test_the_proof_leaves_no_file_and_the_handoff_describes_the_built_tree(history, checkout_root, case_dirs, capsys):
    write_case(case_dirs[0], "greeter_two", clean_case(history))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 0, output
    tree = checkout_root / "greeter_two"
    handoff_relative = f".studio/output/impl_loop/{UNIT}/impl--{UNIT}--writer.json"
    leftovers = git(tree, "status", "--porcelain", "--ignored", "--untracked-files=all")
    assert leftovers == f"?? {handoff_relative}"

    handoff = json.loads((tree / handoff_relative).read_text())
    assert handoff["writer_sha"] == git(tree, "rev-parse", "--short", "HEAD")
    assert history["base"].startswith(handoff["base_sha"])
    assert handoff["files_touched"] == ["app.py", "probe_bang.py", "run_checks.py"]
    assert handoff["load_bearing"] == []
    assert handoff["unit_id"] == UNIT
    assert handoff["stage"] == "writer"
    assert handoff["tests"] == {"command": f"{PYTHON} run_checks.py", "passed": True, "exit_code": 0}
    for required in ("unit_id", "base_sha", "writer_sha", "files_touched", "tests", "mvi_claimed", "mutation_check", "stage"):
        assert required in handoff, required


def test_the_proof_files_from_a_later_commit_never_reach_the_defect_tree(history, checkout_root, case_dirs, capsys):
    write_case(case_dirs[0], "greeter_one", defect_case(history))

    code, output = run_build(history, checkout_root, case_dirs, capsys)

    assert code == 0, output
    tree = checkout_root / "greeter_one"
    assert not (tree / "probe_bang.py").exists()
    assert not list(tree.rglob("__pycache__"))


# --- the command line -------------------------------------------------------


def test_the_command_runs_as_a_script_and_reports_an_empty_case_set(checkout_root, tmp_path):
    script = tmp_path / "editor_measure.py"
    shutil.copy2(STUDIO_DIR / script.name, script)
    result = subprocess.run(
        [sys.executable, str(script), "build", "--root", str(checkout_root)],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(STUDIO_DIR)},
    )
    assert result.returncode == 0, result.stderr
    assert "nothing to build" in result.stdout


def test_the_command_exits_2_on_bad_arguments():
    result = subprocess.run(
        [sys.executable, str(STUDIO_DIR / "editor_measure.py"), "build", "--no-such-flag"],
        capture_output=True, text=True,
    )
    assert result.returncode == 2


def test_the_module_does_not_ship_to_installed_repositories():
    import install

    assert "editor_measure.py" not in install.SOURCE_FILES

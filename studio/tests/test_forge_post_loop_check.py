import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from impl_loop import STUDIO_ROOT

IMPL_LOOP = STUDIO_ROOT / "impl_loop.py"

RECORD_FIELDS = {
    "unit_id",
    "branch",
    "tree",
    "base_sha",
    "test_command",
    "pack_check",
    "started_at",
    "checked_at",
    "problems",
}


def git(directory: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=str(directory), check=True, capture_output=True, text=True,
    )
    return completed.stdout.strip()


def run_impl_loop(directory: Path, *arguments: str) -> subprocess.CompletedProcess:
    environment = {name: value for name, value in os.environ.items() if name != "STUDIO_ARTIFACT_ROOT"}
    return subprocess.run(
        [sys.executable, str(IMPL_LOOP), *arguments],
        cwd=str(directory),
        capture_output=True,
        text=True,
        env=environment,
    )


def record_path(tree: Path) -> Path:
    return Path(git(tree, "rev-parse", "--absolute-git-dir")) / "studio-forge.json"


def read_record(tree: Path) -> dict:
    return json.loads(record_path(tree).read_text(encoding="utf-8"))


@pytest.fixture
def workspace(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "kept.txt").write_text("committed\n")
    git(repo, "add", "kept.txt")
    git(repo, "commit", "-q", "-m", "initial")
    git(repo, "checkout", "-q", "-B", "impl/demo")
    test_log = tmp_path / "tests-ran.log"
    test_command = f"echo ran >> {shlex.quote(str(test_log))} && test ! -e red.flag"
    config = tmp_path / "implementation_loop.toml"
    config.write_text(f"[gate]\ntest_command = {json.dumps(test_command)}\n")
    return {"repo": repo, "config": config, "test_log": test_log, "test_command": test_command, "tmp": tmp_path}


def launch(workspace, *extra: str, directory: Path | None = None) -> subprocess.CompletedProcess:
    return run_impl_loop(
        directory or workspace["repo"], str(workspace["config"]), "--branch", "impl/demo", *extra,
    )


def commit_writer(repo: Path, subject: str = "writer: demo") -> None:
    (repo / "built.txt").write_text("built\n")
    git(repo, "add", "built.txt")
    git(repo, "commit", "-q", "-m", subject)


def write_record(workspace, **overrides) -> Path:
    repo = workspace["repo"]
    record = {
        "unit_id": "demo",
        "branch": "impl/demo",
        "tree": str(repo),
        "base_sha": git(repo, "rev-parse", "HEAD"),
        "test_command": workspace["test_command"],
        "pack_check": None,
        "started_at": "2026-11-26T10:00:00+00:00",
        "checked_at": None,
        "problems": [],
        **overrides,
    }
    path = record_path(repo)
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def check(directory: Path, *extra: str) -> subprocess.CompletedProcess:
    return run_impl_loop(directory, "--check", *extra)


def test_a_launch_writes_the_record_with_its_nine_fields_into_the_tree_git_directory(workspace):
    repo = workspace["repo"]
    head = git(repo, "rev-parse", "HEAD")

    completed = launch(workspace, "--unit", "demo")

    assert completed.returncode == 0, completed.stderr
    knobs = json.loads(completed.stdout)
    assert knobs["test_command"] == workspace["test_command"]
    assert knobs["branch"] == "impl/demo"
    assert record_path(repo).parent == repo.resolve() / ".git"
    record = read_record(repo)
    assert set(record) == RECORD_FIELDS
    assert record == {
        "unit_id": "demo",
        "branch": "impl/demo",
        "tree": str(repo.resolve()),
        "base_sha": head,
        "test_command": workspace["test_command"],
        "pack_check": None,
        "started_at": knobs["launched_at"],
        "checked_at": None,
        "problems": [],
    }
    assert git(repo, "status", "--porcelain") == ""


def test_a_launch_in_a_linked_worktree_writes_into_that_worktree_git_directory(workspace):
    repo = workspace["repo"]
    linked = workspace["tmp"] / "linked"
    git(repo, "checkout", "-q", "-b", "parking")
    git(repo, "worktree", "add", "-q", str(linked), "impl/demo")

    completed = launch(workspace, "--unit", "demo", directory=linked)

    assert completed.returncode == 0, completed.stderr
    linked_record = record_path(linked)
    assert linked_record.parent.parent == repo.resolve() / ".git" / "worktrees"
    assert json.loads(linked_record.read_text())["tree"] == str(linked.resolve())
    assert not (repo / ".git" / "studio-forge.json").exists()


def test_a_launch_records_the_pack_check_it_added_to_the_static_checks(workspace):
    config = workspace["config"]
    config.write_text(
        config.read_text()
        + '\n[packs.game.art]\nasset_command = "node tools/measure.mjs"\nroutes = ["code-built"]\n'
    )
    expected = (
        f'"{sys.executable}" "{STUDIO_ROOT / "run_phase.py"}" check-packs --config "{config.resolve()}"'
    )

    completed = launch(workspace, "--unit", "demo")

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["static_checks"][-1] == expected
    assert read_record(workspace["repo"])["pack_check"] == expected


def test_branch_without_a_unit_id_is_a_usage_error_and_writes_no_record(workspace):
    completed = launch(workspace)

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "--branch needs a unit id" in completed.stderr
    assert "If /forge sent this, the session is running an older copy of the command: restart it." in completed.stderr
    assert not record_path(workspace["repo"]).exists()


def test_a_spec_planning_exactly_one_unit_supplies_the_unit_id(workspace):
    spec = workspace["tmp"] / "one.md"
    spec.write_text("## Build Plan\n\n### 1. `only_unit` — The one thing\n\n- [ ] It works.\n")

    completed = launch(workspace, "--spec", str(spec))

    assert completed.returncode == 0, completed.stderr
    assert read_record(workspace["repo"])["unit_id"] == "only_unit"


def test_a_spec_planning_two_units_does_not_supply_a_unit_id(workspace):
    spec = workspace["tmp"] / "two.md"
    spec.write_text("## Build Plan\n\n### 1. `first_unit` — One\n\n### 2. `second_unit` — Two\n")

    completed = launch(workspace, "--spec", str(spec))

    assert completed.returncode != 0
    assert "--branch needs a unit id" in completed.stderr
    assert not record_path(workspace["repo"]).exists()


def test_no_invocation_without_branch_writes_a_record(workspace):
    repo = workspace["repo"]

    knobs_only = run_impl_loop(repo, str(workspace["config"]), "--unit", "demo")
    checked = check(repo)

    assert knobs_only.returncode == 0, knobs_only.stderr
    assert "launched_at" not in json.loads(knobs_only.stdout)
    assert checked.returncode == 2
    assert not record_path(repo).exists()


def test_a_refused_branch_writes_no_record(workspace):
    (workspace["repo"] / "kept.txt").write_text("edited and not committed\n")

    completed = launch(workspace, "--unit", "demo")

    assert completed.returncode == 1
    assert "dirty-tree" in completed.stderr
    assert not record_path(workspace["repo"]).exists()


def test_launching_over_a_record_never_checked_refuses_and_prints_the_check_command(workspace):
    repo = workspace["repo"]
    first = launch(workspace, "--unit", "demo")
    before = record_path(repo).read_text()

    second = launch(workspace, "--unit", "other_unit")

    assert second.returncode == 1
    assert second.stdout == ""
    assert "unchecked-loop" in second.stderr
    assert "demo" in second.stderr
    assert "impl/demo" in second.stderr
    assert json.loads(first.stdout)["launched_at"] in second.stderr
    expected_command = shlex.join([sys.executable, str(IMPL_LOOP), "--check", "--work-dir", str(repo.resolve())])
    assert expected_command in second.stderr
    assert record_path(repo).read_text() == before


def test_the_printed_check_command_checks_that_tree(workspace):
    repo = workspace["repo"]
    launch(workspace, "--unit", "demo")
    commit_writer(repo)
    refusal = launch(workspace, "--unit", "demo")
    command_line = next(line.strip() for line in refusal.stderr.splitlines() if "--check" in line)

    completed = subprocess.run(command_line, shell=True, capture_output=True, text=True, cwd=str(workspace["tmp"]))

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["clean"] is True
    assert not record_path(repo).exists()


def test_launching_over_an_unreadable_record_refuses_and_names_the_file(workspace):
    repo = workspace["repo"]
    path = record_path(repo)
    path.write_text("{ this is not a record")

    completed = launch(workspace, "--unit", "demo")

    assert completed.returncode == 1
    assert "unreadable-record" in completed.stderr
    assert str(path) in completed.stderr
    assert path.read_text() == "{ this is not a record"


def test_launching_while_another_launch_holds_the_tree_refuses_and_writes_no_record(workspace):
    fcntl = pytest.importorskip("fcntl")
    repo = workspace["repo"]
    lock_path = record_path(repo).with_name("studio-forge.lock")

    with lock_path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held = launch(workspace, "--unit", "demo")
    released = launch(workspace, "--unit", "demo")

    assert held.returncode == 1
    assert held.stdout == ""
    assert "launch-in-progress" in held.stderr
    assert str(lock_path) in held.stderr
    assert released.returncode == 0, released.stderr
    assert read_record(repo)["started_at"] == json.loads(released.stdout)["launched_at"]


def test_launching_over_a_stamped_record_replaces_it(workspace):
    repo = workspace["repo"]
    write_record(
        workspace,
        unit_id="old_unit",
        checked_at="2026-11-26T11:00:00+00:00",
        problems=["tests-failed: the test command exited 1."],
    )

    completed = launch(workspace, "--unit", "demo")

    assert completed.returncode == 0, completed.stderr
    record = read_record(repo)
    assert record["unit_id"] == "demo"
    assert record["checked_at"] is None
    assert record["problems"] == []
    assert record["started_at"] == json.loads(completed.stdout)["launched_at"]


def test_check_is_clean_and_removes_the_record_when_every_check_passes(workspace):
    repo = workspace["repo"]
    launch(workspace, "--unit", "demo")
    commit_writer(repo)

    completed = check(repo)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "clean": True,
        "unit_id": "demo",
        "branch": "impl/demo",
        "tests": {"command": workspace["test_command"], "exit_code": 0},
        "packs": None,
        "problems": [],
    }
    assert workspace["test_log"].read_text() == "ran\n"
    assert not record_path(repo).exists()


def test_check_runs_the_test_command_from_the_tree_root(workspace):
    repo = workspace["repo"]
    write_record(workspace, test_command="test -f kept.txt")
    commit_writer(repo)
    subdirectory = repo / "nested"
    subdirectory.mkdir()

    completed = check(subdirectory)

    assert completed.returncode == 0, completed.stderr


def test_check_runs_a_recorded_pack_check_and_reports_it(workspace):
    repo = workspace["repo"]
    write_record(workspace, pack_check="echo packs fine")
    commit_writer(repo)

    completed = check(repo)

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["packs"] == {"command": "echo packs fine", "exit_code": 0}
    assert "packs fine" in completed.stderr
    assert not record_path(repo).exists()


def test_check_with_work_dir_checks_that_tree_from_anywhere(workspace):
    repo = workspace["repo"]
    launch(workspace, "--unit", "demo")
    commit_writer(repo)
    elsewhere = workspace["tmp"] / "elsewhere"
    elsewhere.mkdir()

    completed = check(elsewhere, "--work-dir", str(repo))

    assert completed.returncode == 0, completed.stderr
    assert not record_path(repo).exists()


def test_wrong_branch_is_reported_stamped_and_runs_neither_tests_nor_packs(workspace):
    repo = workspace["repo"]
    pack_log = workspace["tmp"] / "packs-ran.log"
    write_record(workspace, pack_check=f"echo ran >> {shlex.quote(str(pack_log))}")
    commit_writer(repo)
    git(repo, "checkout", "-q", "-b", "elsewhere")

    completed = check(repo)

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["clean"] is False
    assert [problem["name"] for problem in report["problems"]] == ["wrong-branch"]
    assert report["tests"]["exit_code"] is None
    assert report["packs"]["exit_code"] is None
    assert not workspace["test_log"].exists()
    assert not pack_log.exists()
    record = read_record(repo)
    assert record["checked_at"] is not None
    assert record["problems"][0].startswith("wrong-branch: ")
    assert "wrong-branch: " in completed.stderr


def test_no_writer_commit_is_reported_stamped_and_runs_neither_tests_nor_packs(workspace):
    repo = workspace["repo"]
    pack_log = workspace["tmp"] / "packs-ran.log"
    write_record(workspace, pack_check=f"echo ran >> {shlex.quote(str(pack_log))}")
    commit_writer(repo, "writer(stuck): demo")

    completed = check(repo)

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert [problem["name"] for problem in report["problems"]] == ["no-writer-commit"]
    assert not workspace["test_log"].exists()
    assert not pack_log.exists()
    assert read_record(repo)["problems"][0].startswith("no-writer-commit: ")


def test_a_writer_commit_for_a_longer_unit_id_does_not_count(workspace):
    repo = workspace["repo"]
    write_record(workspace)
    commit_writer(repo, "writer: demo_extra")

    completed = check(repo)

    assert completed.returncode == 1
    assert [problem["name"] for problem in json.loads(completed.stdout)["problems"]] == ["no-writer-commit"]


def test_a_red_test_command_is_tests_failed_and_tells_the_user_what_to_do(workspace):
    repo = workspace["repo"]
    launch(workspace, "--unit", "demo")
    commit_writer(repo)
    (repo / "red.flag").write_text("red\n")

    completed = check(repo)

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["tests"]["exit_code"] != 0
    assert [problem["name"] for problem in report["problems"]] == ["tests-failed"]
    assert "tests-failed: " in completed.stderr
    assert "Fix:" in completed.stderr
    assert "See .claude/commands/forge.md" in completed.stderr
    record = read_record(repo)
    assert record["checked_at"] is not None
    assert record["problems"][0].startswith("tests-failed: ")


def test_a_red_test_command_and_a_red_pack_check_are_both_reported_by_one_check(workspace):
    repo = workspace["repo"]
    write_record(workspace, pack_check="echo 'art.png is over budget'; echo second line; exit 3")
    commit_writer(repo)
    (repo / "red.flag").write_text("red\n")

    completed = check(repo)

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert [problem["name"] for problem in report["problems"]] == ["tests-failed", "packs-failed"]
    assert report["packs"]["exit_code"] == 3
    assert "art.png is over budget" in report["problems"][1]["detail"]
    assert "second line" not in report["problems"][1]["detail"]
    assert workspace["test_log"].read_text() == "ran\n"
    assert len(read_record(repo)["problems"]) == 2


def test_a_stamped_record_is_checked_again_and_passing_removes_it(workspace):
    repo = workspace["repo"]
    launch(workspace, "--unit", "demo")
    commit_writer(repo)
    (repo / "red.flag").write_text("red\n")
    first = check(repo)
    (repo / "red.flag").unlink()

    second = check(repo)

    assert first.returncode == 1
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["clean"] is True
    assert workspace["test_log"].read_text() == "ran\nran\n"
    assert not record_path(repo).exists()


def test_check_without_a_record_exits_2_and_runs_nothing(workspace):
    completed = check(workspace["repo"])

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "Nothing to check" in completed.stderr
    assert not workspace["test_log"].exists()


@pytest.mark.parametrize(
    "contents",
    ["{ broken", "[]", json.dumps({"unit_id": "demo"})],
    ids=["not-json", "not-an-object", "missing-fields"],
)
def test_check_over_an_unreadable_record_exits_2_names_the_file_and_runs_no_test(workspace, contents):
    repo = workspace["repo"]
    commit_writer(repo)
    path = record_path(repo)
    path.write_text(contents)

    completed = check(repo)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert str(path) in completed.stderr
    assert not workspace["test_log"].exists()
    assert path.read_text() == contents


def test_check_outside_a_git_tree_or_with_a_bad_work_dir_exits_2(workspace, tmp_path):
    outside = tmp_path / "plain"
    outside.mkdir()

    not_a_tree = check(outside)
    bad_work_dir = check(workspace["repo"], "--work-dir", str(tmp_path / "absent"))
    mixed_arguments = check(workspace["repo"], "--branch", "impl/demo")

    assert not_a_tree.returncode == 2
    assert bad_work_dir.returncode == 2
    assert mixed_arguments.returncode == 2
    assert "Traceback" not in not_a_tree.stderr + bad_work_dir.stderr

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
    "suites",
    "gate_config",
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


def test_a_launch_writes_the_record_with_its_eleven_fields_into_the_tree_git_directory(workspace):
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
        "suites": {},
        "gate_config": None,
        "started_at": knobs["launched_at"],
        "checked_at": None,
        "problems": [],
    }
    assert git(repo, "status", "--porcelain") == ""


@pytest.mark.parametrize("spelling", ["only", "only.md"])
def test_a_launch_infers_the_unit_from_a_one_unit_spec_spelled_either_way(workspace, spelling):
    repo = workspace["repo"]
    specs = repo / ".studio" / "specs"
    specs.mkdir(parents=True)
    (specs / "only.md").write_text("## Build Plan\n### 1. `solo_unit` \u2014 Does one thing\n- [ ] It works.\n")
    git(repo, "add", ".studio")
    git(repo, "commit", "-q", "-m", "spec")

    completed = launch(workspace, "--spec", spelling)

    assert completed.returncode == 0, completed.stderr
    assert read_record(repo)["unit_id"] == "solo_unit"


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


def test_launching_while_another_run_holds_the_tree_refuses_and_writes_no_record(workspace):
    repo = workspace["repo"]
    lock_path = record_path(repo).with_name("studio-forge.lock")

    lock_path.write_text("")
    held = launch(workspace, "--unit", "demo")
    held_wrote_record = record_path(repo).exists()
    assert lock_path.exists()
    lock_path.unlink()
    released = launch(workspace, "--unit", "demo")

    assert held.returncode == 1
    assert held.stdout == ""
    assert "launch-in-progress" in held.stderr
    assert str(lock_path) in held.stderr
    assert not held_wrote_record
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
        "tests": [{"suite": None, "command": workspace["test_command"], "exit_code": 0}],
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
    assert report["tests"] == []
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
    assert [test_run["suite"] for test_run in report["tests"]] == [None]
    assert report["tests"][0]["exit_code"] != 0
    assert [problem["name"] for problem in report["problems"]] == ["tests-failed"]
    assert report["problems"][0]["detail"].startswith("the default test command ")
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


def test_a_launch_while_a_stamped_record_is_checked_again_refuses_instead_of_replacing_it(workspace):
    repo = workspace["repo"]
    launch_log = workspace["tmp"] / "inner-launch.log"
    inner_launch = shlex.join([
        sys.executable, str(IMPL_LOOP), str(workspace["config"]), "--branch", "impl/demo", "--unit", "other",
    ])
    write_record(
        workspace,
        test_command=f"{inner_launch} > {shlex.quote(str(launch_log))} 2>&1; true",
        checked_at="2026-11-26T11:00:00+00:00",
        problems=["tests-failed: the test command exited 1."],
    )
    commit_writer(repo)

    completed = check(repo)

    assert completed.returncode == 0, completed.stderr
    assert "launch-in-progress" in launch_log.read_text()
    assert not record_path(repo).exists()


def test_check_while_another_run_holds_the_tree_exits_2_and_runs_no_test(workspace):
    repo = workspace["repo"]
    commit_writer(repo)
    path = write_record(workspace)
    lock_path = path.with_name("studio-forge.lock")

    lock_path.write_text("")
    held = check(repo)

    assert held.returncode == 2
    assert held.stdout == ""
    assert str(lock_path) in held.stderr
    assert lock_path.exists()
    assert not workspace["test_log"].exists()
    assert read_record(repo)["checked_at"] is None


def test_launch_and_check_leave_no_lock_behind_for_the_portable_host(workspace):
    repo = workspace["repo"]
    lock_path = record_path(repo).with_name("studio-forge.lock")

    empty = check(repo)
    assert empty.returncode == 2
    assert not lock_path.exists()

    launched = launch(workspace, "--unit", "demo")
    assert launched.returncode == 0, launched.stderr
    assert not lock_path.exists()

    commit_writer(repo)
    checked = check(repo)
    assert checked.returncode == 0, checked.stderr
    assert not lock_path.exists()


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


def logged_command(name: str, log: Path, red_flag: Path) -> str:
    return f"echo {name} >> {shlex.quote(str(log))}; test ! -e {shlex.quote(str(red_flag))}"


@pytest.fixture
def suited(tmp_path):
    repo = tmp_path / "repo"
    for folder in ("web", "unity", "shared", ".studio"):
        (repo / folder).mkdir(parents=True)
    (repo / "web" / "app.js").write_text("app\n")
    (repo / "unity" / "Game.cs").write_text("game\n")
    (repo / "shared" / "schema.json").write_text("{}\n")
    (repo / "README.md").write_text("readme\n")
    log = tmp_path / "suites-ran.log"
    commands = {name: logged_command(name, log, tmp_path / f"{name}.red") for name in ("web", "unity", "default")}
    config = repo / ".studio" / "implementation_loop.toml"
    config.write_text(
        f"[gate]\ntest_command = {json.dumps(commands['default'])}\n\n"
        f"[gate.suites.web]\ncommand = {json.dumps(commands['web'])}\n"
        'paths = ["web/", "shared/schema.json"]\n\n'
        f"[gate.suites.unity]\ncommand = {json.dumps(commands['unity'])}\n"
        'paths = ["unity/", "shared/schema.json"]\n'
    )
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "initial")
    git(repo, "checkout", "-q", "-B", "impl/demo")
    return {"repo": repo, "config": config, "log": log, "commands": commands, "tmp": tmp_path}


def launch_suited(suited) -> subprocess.CompletedProcess:
    completed = run_impl_loop(suited["repo"], str(suited["config"]), "--branch", "impl/demo", "--unit", "demo")
    assert completed.returncode == 0, completed.stderr
    return completed


def commit_everything(repo: Path, subject: str = "writer: demo") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", subject)


def suites_ran(suited) -> list[str]:
    if not suited["log"].exists():
        return []
    return suited["log"].read_text().split()


def change_web(repo: Path) -> None:
    (repo / "web" / "app.js").write_text("changed\n")
    commit_everything(repo)


def rename_web_to_unity(repo: Path) -> None:
    git(repo, "mv", "web/app.js", "unity/app.js")
    commit_everything(repo)


def delete_under_unity(repo: Path) -> None:
    git(repo, "rm", "-q", "unity/Game.cs")
    commit_everything(repo)


def add_untracked_outside_every_suite(repo: Path) -> None:
    commit_everything(repo)
    (repo / "notes.txt").write_text("untracked\n")


def change_only_a_concerns_file(repo: Path) -> None:
    (repo / "reviewer-concerns").mkdir()
    (repo / "reviewer-concerns" / "demo.md").write_text("concern\n")
    commit_everything(repo)
    handoffs = repo / ".studio" / "output" / "impl_loop" / "demo"
    handoffs.mkdir(parents=True)
    (handoffs / "impl--demo--writer.json").write_text("{}\n")


def change_a_file_under_two_suites(repo: Path) -> None:
    (repo / "shared" / "schema.json").write_text('{"changed": true}\n')
    commit_everything(repo)


def change_nothing(repo: Path) -> None:
    commit_everything(repo)


def change_web_and_the_readme(repo: Path) -> None:
    (repo / "web" / "app.js").write_text("changed\n")
    (repo / "README.md").write_text("changed\n")
    commit_everything(repo)


@pytest.mark.parametrize(
    ("make_change", "expected"),
    [
        (change_web, ["web"]),
        (rename_web_to_unity, ["web", "unity"]),
        (delete_under_unity, ["unity"]),
        (add_untracked_outside_every_suite, ["default"]),
        (change_only_a_concerns_file, ["default"]),
        (change_a_file_under_two_suites, ["web", "unity"]),
        (change_nothing, ["default"]),
        (change_web_and_the_readme, ["web", "default"]),
    ],
    ids=[
        "web-only", "rename-web-to-unity", "deletion-under-unity", "untracked-outside-every-suite",
        "only-a-concerns-file", "file-under-two-suites", "empty-diff", "web-and-unclaimed",
    ],
)
def test_check_runs_exactly_the_suites_the_changes_fall_under_plus_the_default(suited, make_change, expected):
    launch_suited(suited)
    make_change(suited["repo"])

    completed = check(suited["repo"])

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert [test_run["suite"] or "default" for test_run in report["tests"]] == expected
    assert suites_ran(suited) == expected
    assert report["problems"] == []
    assert not record_path(suited["repo"]).exists()


def test_tests_lists_each_run_in_file_order_with_the_default_last(suited):
    launch_suited(suited)
    (suited["repo"] / "unity" / "Game.cs").write_text("changed\n")
    (suited["repo"] / "web" / "app.js").write_text("changed\n")
    (suited["repo"] / "README.md").write_text("changed\n")
    commit_everything(suited["repo"])

    completed = check(suited["repo"])

    commands = suited["commands"]
    assert json.loads(completed.stdout)["tests"] == [
        {"suite": "web", "command": commands["web"], "exit_code": 0},
        {"suite": "unity", "command": commands["unity"], "exit_code": 0},
        {"suite": None, "command": commands["default"], "exit_code": 0},
    ]


def test_every_routed_command_runs_and_each_red_one_is_its_own_tests_failed_problem(suited):
    launch_suited(suited)
    change_web_and_the_readme(suited["repo"])
    (suited["tmp"] / "web.red").write_text("red\n")
    (suited["tmp"] / "default.red").write_text("red\n")

    completed = check(suited["repo"])

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert suites_ran(suited) == ["web", "default"]
    assert [(test_run["suite"], test_run["exit_code"]) for test_run in report["tests"]] == [("web", 1), (None, 1)]
    assert [problem["name"] for problem in report["problems"]] == ["tests-failed", "tests-failed"]
    assert report["problems"][0]["detail"] == f"the web suite's command `{suited['commands']['web']}` exited 1."
    assert report["problems"][1]["detail"] == (
        f"the default test command `{suited['commands']['default']}` exited 1."
    )
    assert len(read_record(suited["repo"])["problems"]) == 2


def test_a_red_suite_fails_the_check_while_the_default_is_green(suited):
    launch_suited(suited)
    change_web(suited["repo"])
    (suited["tmp"] / "web.red").write_text("red\n")

    completed = check(suited["repo"])

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert [problem["name"] for problem in report["problems"]] == ["tests-failed"]
    assert "the web suite's command" in report["problems"][0]["detail"]


def test_an_edit_to_the_gate_config_is_flagged_the_tests_still_run_and_rechecking_keeps_it(suited):
    launch_suited(suited)
    config = suited["config"]
    config.write_text(config.read_text().replace('paths = ["web/", "shared/schema.json"]', 'paths = ["shared/schema.json"]'))
    (suited["repo"] / "web" / "app.js").write_text("changed\n")
    commit_everything(suited["repo"])
    path = record_path(suited["repo"])

    first = check(suited["repo"])
    second = check(suited["repo"])

    assert first.returncode == 1
    report = json.loads(first.stdout)
    assert [problem["name"] for problem in report["problems"]] == ["gate-config-changed"]
    base_sha = read_record(suited["repo"])["base_sha"]
    assert report["problems"][0]["detail"] == (
        f".studio/implementation_loop.toml changed since {base_sha}, so the next launch on this branch would be "
        "gated by a config this unit wrote; a person should read that change."
    )
    assert [test_run["suite"] or "default" for test_run in report["tests"]] == ["web", "default"]
    fix_line = next(line for line in first.stderr.splitlines() if line.strip().startswith("Fix:"))
    assert str(path) in fix_line
    assert "delete" in fix_line
    assert second.returncode == 1
    assert [problem["name"] for problem in json.loads(second.stdout)["problems"]] == ["gate-config-changed"]
    assert path.exists()


def test_the_pack_check_still_runs_and_reports_beside_the_routed_suites(suited):
    launch_suited(suited)
    record = json.loads(record_path(suited["repo"]).read_text())
    record["pack_check"] = "echo 'art.png is over budget'; exit 3"
    record_path(suited["repo"]).write_text(json.dumps(record))
    change_web(suited["repo"])

    completed = check(suited["repo"])

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["packs"] == {"command": "echo 'art.png is over budget'; exit 3", "exit_code": 3}
    assert [problem["name"] for problem in report["problems"]] == ["packs-failed"]
    assert suites_ran(suited) == ["web"]


def test_a_launch_writes_the_loaded_suites_and_the_gate_config_into_the_record_and_knobs(suited):
    completed = launch_suited(suited)

    commands = suited["commands"]
    expected_suites = {
        "web": {"command": commands["web"], "paths": ["web/", "shared/schema.json"]},
        "unity": {"command": commands["unity"], "paths": ["unity/", "shared/schema.json"]},
    }
    knobs = json.loads(completed.stdout)
    record = read_record(suited["repo"])
    assert set(record) == RECORD_FIELDS
    assert record["suites"] == expected_suites
    assert record["gate_config"] == ".studio/implementation_loop.toml"
    assert knobs["suites"] == expected_suites
    assert knobs["gate_config"] == ".studio/implementation_loop.toml"
    assert record["test_command"] == commands["default"]


def test_a_record_without_suites_or_gate_config_runs_only_its_test_command(suited):
    repo = suited["repo"]
    write_record({"repo": repo, "test_command": suited["commands"]["default"]})
    change_web(repo)
    suited["config"].write_text("[gate]\ntest_command = \"true\"\n")
    commit_everything(repo, "writer: demo again")

    completed = check(repo)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["tests"] == [
        {"suite": None, "command": suited["commands"]["default"], "exit_code": 0},
    ]
    assert suites_ran(suited) == ["default"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("suites", {"web": {"command": "true"}}), ("suites", []), ("gate_config", 5)],
    ids=["suite-without-paths", "suites-not-a-table", "gate-config-not-text"],
)
def test_a_record_with_a_malformed_new_field_is_unreadable_and_runs_no_test(suited, field, value):
    repo = suited["repo"]
    path = write_record({"repo": repo, "test_command": suited["commands"]["default"]}, **{field: value})
    change_web(repo)

    completed = check(repo)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert str(path) in completed.stderr
    assert field in completed.stderr
    assert suites_ran(suited) == []


@pytest.mark.parametrize(
    ("suite_table", "reason"),
    [
        ('suites = "web"\n', "gate.suites is not a table"),
        ('[gate.suites]\nweb = "x"\n', "is not a table"),
        ('[gate.suites.web]\ncommand = "c"\npaths = ["web/"]\npath = ["web/"]\n', 'has unknown key "path"'),
        ('[gate.suites.web]\ncommand = ""\npaths = ["web/"]\n', "has no command"),
        ('[gate.suites.web]\ncommand = "c"\npaths = []\n', "has no paths"),
        ('[gate.suites.web]\ncommand = "c"\npaths = ["/web/"]\n', "must be repo-relative"),
        ('[gate.suites.web]\ncommand = "c"\npaths = ["web/*.js"]\n', "has a glob character"),
        ('[gate.suites.web]\ncommand = "c"\npaths = ["wbe/"]\n', "does not exist as written"),
        ('[gate.suites.web]\ncommand = "c"\npaths = ["web"]\n', 'does not exist as written, write "web/"'),
    ],
    ids=[
        "suites-not-a-table", "suite-not-a-table", "unknown-key", "blank-command", "empty-paths",
        "not-repo-relative", "glob", "missing-path", "folder-without-slash",
    ],
)
def test_each_bad_suite_makes_impl_loop_exit_1_naming_the_file_and_the_suite(suited, suite_table, reason):
    config = suited["config"]
    config.write_text('[gate]\ntest_command = "true"\n' + suite_table)

    knobs_only = run_impl_loop(suited["repo"], str(config))
    launched = run_impl_loop(suited["repo"], str(config), "--branch", "impl/demo", "--unit", "demo")

    for completed in (knobs_only, launched):
        assert completed.returncode == 1
        assert completed.stdout == ""
        assert completed.stderr.startswith("bad-suite: [gate.suites")
        assert str(config.resolve()) in completed.stderr
        assert reason in completed.stderr
        assert "Fix:" in completed.stderr
    if reason != "gate.suites is not a table":
        assert "[gate.suites.web]" in knobs_only.stderr
    assert not record_path(suited["repo"]).exists()


def test_a_config_without_suites_gives_the_same_knobs_plus_empty_suites_and_its_gate_config(workspace, suited):
    from impl_loop import load_knobs, load_loop_config, runtime_knobs

    outside = workspace["config"]
    inside = suited["repo"] / ".studio" / "plain.toml"
    inside.write_text(outside.read_text())

    assert load_knobs(outside) == {**runtime_knobs(load_loop_config(outside)), "suites": {}, "gate_config": None}
    assert load_knobs(inside) == {
        **runtime_knobs(load_loop_config(inside)), "suites": {}, "gate_config": ".studio/plain.toml",
    }


def test_a_failed_git_listing_is_a_could_not_check_that_runs_no_test(suited, monkeypatch, capsys):
    import gate_routes
    from impl_loop import CheckError, check_loop

    launch_suited(suited)
    change_web(suited["repo"])
    before = record_path(suited["repo"]).read_text()

    def refuse(root, base_sha):
        raise gate_routes.RoutesError("`git diff` failed")

    monkeypatch.setattr(gate_routes, "changed_files", refuse)

    with pytest.raises(CheckError) as raised:
        check_loop(suited["repo"])

    assert "No test was run" in str(raised.value)
    assert suites_ran(suited) == []
    assert record_path(suited["repo"]).read_text() == before
    assert not record_path(suited["repo"]).with_name("studio-forge.lock").exists()

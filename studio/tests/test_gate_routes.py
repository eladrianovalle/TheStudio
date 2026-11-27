import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

import gate_routes
from gate_routes import RoutesError, SuiteError, changed_files, check_suites, config_changed, route, run
from impl_loop import STUDIO_ROOT

SOURCE = "/repo/.studio/implementation_loop.toml"


def git(directory: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=str(directory), check=True, capture_output=True, text=True,
    )
    return completed.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "web").mkdir(parents=True)
    (root / "unity").mkdir()
    (root / "shared").mkdir()
    (root / "web" / "app.js").write_text("app\n")
    (root / "unity" / "Game.cs").write_text("game\n")
    (root / "shared" / "schema.json").write_text("{}\n")
    (root / "README.md").write_text("readme\n")
    (root / ".gitignore").write_text("build/\n")
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "initial")
    return root


def suite(command: str, *paths: str) -> dict:
    return {"command": command, "paths": list(paths)}


SUITES = {
    "web": suite("web-check", "web/", "shared/schema.json"),
    "unity": suite("unity-check", "unity/", "shared/schema.json"),
}


def test_valid_suites_load_in_file_order_as_command_and_paths(repo):
    table = {
        "web": {"paths": ["web/", "shared/schema.json"], "command": "npm --prefix web run check"},
        "unity": {"command": "./run-editmode.sh", "paths": ["unity/"]},
    }

    suites = check_suites(table, repo, SOURCE)

    assert list(suites) == ["web", "unity"]
    assert suites == {
        "web": {"command": "npm --prefix web run check", "paths": ["web/", "shared/schema.json"]},
        "unity": {"command": "./run-editmode.sh", "paths": ["unity/"]},
    }


def test_no_suites_at_all_is_an_empty_table(repo):
    assert check_suites({}, repo, SOURCE) == {}


def test_a_suites_value_that_is_not_a_table_is_refused():
    with pytest.raises(SuiteError) as raised:
        check_suites("web", None, SOURCE)

    assert str(raised.value) == f"bad-suite: [gate.suites] in {SOURCE} gate.suites is not a table."
    assert raised.value.fix


@pytest.mark.parametrize(
    ("web_suite", "reason"),
    [
        ("x", "is not a table"),
        ({"command": "c", "paths": ["web/"], "path": ["web/"]},
         'has unknown key "path"; a suite takes only command and paths'),
        ({"paths": ["web/"]}, "has no command, or it is blank or not text"),
        ({"command": "  ", "paths": ["web/"]}, "has no command, or it is blank or not text"),
        ({"command": 5, "paths": ["web/"]}, "has no command, or it is blank or not text"),
        ({"command": "c"}, "has no paths, or it is empty or not a list of text"),
        ({"command": "c", "paths": []}, "has no paths, or it is empty or not a list of text"),
        ({"command": "c", "paths": "web/"}, "has no paths, or it is empty or not a list of text"),
        ({"command": "c", "paths": ["web/", 3]}, "has no paths, or it is empty or not a list of text"),
        ({"command": "c", "paths": ["/web/"]}, 'path "/web/" must be repo-relative'),
        ({"command": "c", "paths": ["web\\app.js"]}, 'path "web\\app.js" must be repo-relative'),
        ({"command": "c", "paths": ["web/../unity/"]}, 'path "web/../unity/" must be repo-relative'),
        ({"command": "c", "paths": ["../web/"]}, 'path "../web/" must be repo-relative'),
        ({"command": "c", "paths": ["./web/"]}, 'path "./web/" must be repo-relative'),
        ({"command": "c", "paths": [" "]}, 'path " " must be repo-relative'),
        ({"command": "c", "paths": ["web//"]}, 'path "web//" must be repo-relative'),
        ({"command": "c", "paths": ["web/./"]}, 'path "web/./" must be repo-relative'),
        ({"command": "c", "paths": ["web/*.js"]}, 'path "web/*.js" has a glob character'),
        ({"command": "c", "paths": ["web/app?.js"]}, 'path "web/app?.js" has a glob character'),
        ({"command": "c", "paths": ["web/[ab].js"]}, 'path "web/[ab].js" has a glob character'),
    ],
    ids=[
        "not-a-table", "unknown-key", "no-command", "blank-command", "command-not-text",
        "no-paths", "empty-paths", "paths-not-a-list", "path-not-text", "leading-slash", "backslash",
        "dot-dot-inside", "dot-dot-leading", "leading-dot-slash", "blank-path", "empty-segment", "dot-segment",
        "star", "question-mark",
        "bracket",
    ],
)
def test_each_refusal_names_the_file_the_suite_and_the_reason(web_suite, reason):
    with pytest.raises(SuiteError) as raised:
        check_suites({"unity": suite("u", "unity/"), "web": web_suite}, None, SOURCE)

    assert str(raised.value) == f"bad-suite: [gate.suites.web] in {SOURCE} {reason}."
    assert raised.value.fix


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("wbe/", 'path "wbe/" does not exist as written'),
        ("web/app.js/", 'path "web/app.js/" does not exist as written'),
        ("web/missing.js", 'path "web/missing.js" does not exist as written'),
        ("web", 'path "web" does not exist as written, write "web/"'),
    ],
    ids=["missing-folder", "file-written-as-folder", "missing-file", "folder-written-as-file"],
)
def test_a_path_that_does_not_exist_as_written_is_refused_at_launch(repo, path, reason):
    with pytest.raises(SuiteError) as raised:
        check_suites({"web": suite("c", path)}, repo, SOURCE)

    assert str(raised.value) == f"bad-suite: [gate.suites.web] in {SOURCE} {reason}."


def test_without_a_root_the_filesystem_is_not_consulted():
    assert check_suites({"web": suite("c", "wbe/")}, None, SOURCE) == {"web": suite("c", "wbe/")}


def test_an_existing_folder_and_file_are_accepted(repo):
    assert check_suites({"web": suite("c", "web/", "shared/schema.json")}, repo, SOURCE)


def test_a_change_under_one_suite_routes_only_that_suite():
    routes, unclaimed = route(SUITES, "default", ["web/app.js"])

    assert routes == [{"suite": "web", "command": "web-check"}]
    assert unclaimed == []


def test_a_change_under_two_suites_routes_both_in_file_order():
    routes, unclaimed = route(SUITES, "default", ["shared/schema.json"])

    assert routes == [{"suite": "web", "command": "web-check"}, {"suite": "unity", "command": "unity-check"}]
    assert unclaimed == []


def test_an_unclaimed_change_routes_the_default_last_and_is_named():
    routes, unclaimed = route(SUITES, "default", ["README.md", "unity/Game.cs", "web/app.js"])

    assert [gate["suite"] for gate in routes] == ["web", "unity", None]
    assert routes[-1] == {"suite": None, "command": "default"}
    assert unclaimed == ["README.md"]


def test_nothing_changed_routes_only_the_default():
    routes, unclaimed = route(SUITES, "default", [])

    assert routes == [{"suite": None, "command": "default"}]
    assert unclaimed == []


def test_no_suites_routes_every_change_to_the_default():
    routes, unclaimed = route({}, "default", ["web/app.js"])

    assert routes == [{"suite": None, "command": "default"}]
    assert unclaimed == ["web/app.js"]


@pytest.mark.parametrize("changed", ["webby/app.js", "web.txt", "shared/schema.json.bak", "shared/schema"])
def test_a_folder_covers_only_files_under_it_and_a_file_covers_only_itself(changed):
    routes, unclaimed = route(SUITES, "default", [changed])

    assert routes == [{"suite": None, "command": "default"}]
    assert unclaimed == [changed]


def test_paths_match_case_sensitively():
    routes, _ = route(SUITES, "default", ["Web/app.js"])

    assert [gate["suite"] for gate in routes] == [None]


def test_changed_files_holds_committed_staged_unstaged_deleted_and_untracked_changes(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "web" / "app.js").write_text("committed\n")
    git(repo, "commit", "-q", "-am", "writer: demo")
    (repo / "README.md").write_text("unstaged\n")
    (repo / "shared" / "new.json").write_text("staged\n")
    git(repo, "add", "shared/new.json")
    (repo / "unity" / "Game.cs").unlink()
    (repo / "notes.txt").write_text("untracked\n")
    (repo / "build").mkdir()
    (repo / "build" / "out.bin").write_text("ignored\n")

    assert changed_files(repo, base) == ["README.md", "notes.txt", "shared/new.json", "unity/Game.cs", "web/app.js"]


def test_a_rename_lists_both_its_old_and_new_paths(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "mv", "web/app.js", "unity/app.js")
    git(repo, "commit", "-q", "-m", "writer: demo")

    changed = changed_files(repo, base)

    assert changed == ["unity/app.js", "web/app.js"]
    assert [gate["suite"] for gate in route(SUITES, "default", changed)[0]] == ["web", "unity"]


def test_run_records_and_concerns_files_are_dropped(repo):
    base = git(repo, "rev-parse", "HEAD")
    record_folder = repo / ".studio" / "output" / "impl_loop" / "demo"
    record_folder.mkdir(parents=True)
    (record_folder / "impl--demo--writer.json").write_text("{}\n")
    (repo / "reviewer-concerns").mkdir()
    (repo / "reviewer-concerns" / "demo.md").write_text("concern\n")
    git(repo, "add", "reviewer-concerns")
    git(repo, "commit", "-q", "-m", "writer: demo")
    (repo / ".studio" / "implementation_loop.toml").write_text("[gate]\n")

    assert changed_files(repo, base) == [".studio/implementation_loop.toml"]


def test_a_failed_git_call_raises_routes_error(repo):
    with pytest.raises(RoutesError) as raised:
        changed_files(repo, "0123456789abcdef0123456789abcdef01234567")

    assert "git diff" in str(raised.value)
    assert "fatal:" in str(raised.value)


def test_config_changed_is_true_only_when_the_gate_config_is_listed(repo):
    base = git(repo, "rev-parse", "HEAD")
    config = repo / ".studio" / "implementation_loop.toml"
    config.parent.mkdir()
    config.write_text("[gate]\n")

    assert config_changed(repo, base, ".studio/implementation_loop.toml") is True
    assert config_changed(repo, base, "shared/schema.json") is False
    assert config_changed(repo, base, None) is False


def test_config_changed_is_worked_out_before_run_records_are_dropped(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "reviewer-concerns").mkdir()
    (repo / "reviewer-concerns" / "gate.toml").write_text("[gate]\n")

    assert config_changed(repo, base, "reviewer-concerns/gate.toml") is True
    assert changed_files(repo, base) == []


def test_run_runs_every_route_from_the_root_even_after_a_failure_with_output_on_stderr(repo, capfd):
    routes = [
        {"suite": "web", "command": "echo web-ran; test -f web/app.js && exit 3"},
        {"suite": "unity", "command": "echo unity-ran; test -f unity/Game.cs"},
        {"suite": None, "command": "echo default-ran; exit 1"},
    ]

    results = run(repo, routes)

    assert results == [
        {"suite": "web", "command": routes[0]["command"], "exit_code": 3},
        {"suite": "unity", "command": routes[1]["command"], "exit_code": 0},
        {"suite": None, "command": routes[2]["command"], "exit_code": 1},
    ]
    printed = capfd.readouterr()
    assert printed.out == ""
    assert printed.err.split() == ["web-ran", "unity-ran", "default-ran"]


def test_gate_routes_imports_only_the_standard_library():
    tree = ast.parse((STUDIO_ROOT / "gate_routes.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    studio_modules = {path.stem for path in STUDIO_ROOT.glob("*.py")}

    assert imported <= {"__future__", "argparse", "hashlib", "json", "subprocess", "sys", "pathlib", "tomllib", "tomli"}
    assert not imported & studio_modules
    assert Path(gate_routes.__file__).resolve() == STUDIO_ROOT / "gate_routes.py"


def test_gate_routes_ships_to_installed_repositories():
    import install

    assert "gate_routes.py" in install.SOURCE_FILES


def gate_command_line(repo: Path, gate: object, base: str) -> subprocess.CompletedProcess:
    stdin = gate if isinstance(gate, str) else json.dumps(gate)
    return subprocess.run(
        [sys.executable, str(STUDIO_ROOT / "gate_routes.py"), "--gate", "-", "--base", base],
        cwd=str(repo), input=stdin, capture_output=True, text=True,
    )


def gate_input(**overrides) -> dict:
    gate = {
        "test_command": "echo default-ran",
        "suites": {"web": suite("echo web-ran", "web/"), "unity": suite("echo unity-ran", "unity/")},
        "gate_config": ".studio/implementation_loop.toml",
    }
    return {**gate, **overrides}


@pytest.mark.parametrize("edit", ["weakened", "deleted", "untouched"])
def test_the_command_line_flags_an_edit_to_an_ignored_gate_config_against_its_launch_digest(repo, edit):
    import hashlib

    config = repo / "local-gate.toml"
    config.write_text("[gate]\ntest_command = \"true\"\n")
    (repo / ".gitignore").write_text("local-gate.toml\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "ignore the local gate")
    base = git(repo, "rev-parse", "HEAD")
    digest = hashlib.sha256(config.read_bytes()).hexdigest()
    if edit == "weakened":
        config.write_text("[gate]\ntest_command = \"true\"\n[gate.suites.web]\n")
    elif edit == "deleted":
        config.unlink()

    completed = gate_command_line(repo, gate_input(gate_config="local-gate.toml", gate_config_sha256=digest), base)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["config_changed"] is (edit != "untouched")


def test_the_command_line_runs_the_routed_suites_and_prints_the_runs_on_stdout(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "web" / "app.js").write_text("changed\n")
    (repo / "notes.txt").write_text("new\n")

    completed = gate_command_line(repo, gate_input(), base)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "runs": [
            {"suite": "web", "command": "echo web-ran", "exit_code": 0},
            {"suite": None, "command": "echo default-ran", "exit_code": 0},
        ],
        "unclaimed": ["notes.txt"],
        "config_changed": False,
    }
    assert completed.stderr.split() == ["web-ran", "default-ran"]


def test_the_command_line_exits_1_when_any_run_fails_and_still_runs_the_rest(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "web" / "app.js").write_text("changed\n")
    (repo / "unity" / "Game.cs").write_text("changed\n")
    gate = gate_input(suites={"web": suite("exit 4", "web/"), "unity": suite("echo unity-ran", "unity/")})

    completed = gate_command_line(repo, gate, base)

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["runs"] == [
        {"suite": "web", "command": "exit 4", "exit_code": 4},
        {"suite": "unity", "command": "echo unity-ran", "exit_code": 0},
    ]


def test_the_command_line_reports_a_config_edit_without_changing_the_exit_code(repo):
    base = git(repo, "rev-parse", "HEAD")
    (repo / "README.md").write_text("edited\n")

    completed = gate_command_line(repo, gate_input(gate_config="README.md"), base)

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["config_changed"] is True
    assert report["runs"] == [{"suite": None, "command": "echo default-ran", "exit_code": 0}]


@pytest.mark.parametrize(
    "gate",
    [
        "not json",
        json.dumps(["test_command"]),
        json.dumps({"test_command": "true", "suites": {}}),
        json.dumps({"test_command": "true", "suites": {}, "gate_config": None, "extra": 1}),
        json.dumps({"test_command": " ", "suites": {}, "gate_config": None}),
        json.dumps({"test_command": "true", "suites": {"web": {"command": "x"}}, "gate_config": None}),
        json.dumps({"test_command": "true", "suites": {}, "gate_config": 5}),
    ],
)
def test_the_command_line_exits_2_on_bad_input_without_running_anything(repo, gate):
    base = git(repo, "rev-parse", "HEAD")

    completed = gate_command_line(repo, gate, base)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr.startswith("gate_routes: ")


def test_the_command_line_exits_2_when_git_fails(repo):
    completed = gate_command_line(repo, gate_input(), "0" * 40)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "failed" in completed.stderr
    assert "default-ran" not in completed.stderr


CONFIG = (
    '[gate]\ntest_command = "echo default-ran"\n'
    '[gate.suites.web]\ncommand = "echo web-ran"\npaths = ["web/"]\n'
    '[gate.suites.unity]\ncommand = "echo unity-ran"\npaths = ["unity/"]\n'
)


def config_command_line(repo: Path, config: Path, base: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(STUDIO_ROOT / "gate_routes.py"), "--config", str(config), "--base", base],
        cwd=str(repo), capture_output=True, text=True,
    )


@pytest.fixture
def configured(repo):
    config = repo / ".studio" / "implementation_loop.toml"
    config.parent.mkdir()
    config.write_text(CONFIG)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "gate config")
    return config


@pytest.mark.parametrize(
    "change",
    ["web only", "web red", "unclaimed", "nothing", "config edit"],
)
def test_the_config_command_line_prints_and_exits_exactly_as_the_gate_command_line(repo, configured, change):
    base = git(repo, "rev-parse", "HEAD")
    suites = {"web": suite("echo web-ran", "web/"), "unity": suite("echo unity-ran", "unity/")}
    if change == "web only":
        (repo / "web" / "app.js").write_text("changed\n")
    elif change == "web red":
        configured.write_text(CONFIG.replace('"echo web-ran"', '"exit 4"'))
        git(repo, "commit", "-q", "-am", "red web suite")
        base = git(repo, "rev-parse", "HEAD")
        suites["web"] = suite("exit 4", "web/")
        (repo / "web" / "app.js").write_text("changed\n")
    elif change == "unclaimed":
        (repo / "notes.txt").write_text("new\n")
    elif change == "config edit":
        configured.write_text(CONFIG.replace("[gate]\n", "[gate]\nstatic_checks = []\n", 1))
    gate = gate_input(suites=suites, gate_config=".studio/implementation_loop.toml")

    from_config = config_command_line(repo, configured, base)
    from_gate = gate_command_line(repo, gate, base)

    assert from_config.returncode == from_gate.returncode
    assert from_config.stdout == from_gate.stdout
    assert from_config.stderr == from_gate.stderr
    assert json.loads(from_config.stdout)["config_changed"] is (change == "config edit")
    assert from_config.returncode == (1 if change == "web red" else 0)


def test_the_config_command_line_routes_a_config_outside_any_repository_with_no_config_flag(repo, tmp_path):
    outside = tmp_path / "outside" / "gate.toml"
    outside.parent.mkdir()
    outside.write_text('[gate]\ntest_command = "echo default-ran"\n')
    base = git(repo, "rev-parse", "HEAD")

    completed = config_command_line(repo, outside, base)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "runs": [{"suite": None, "command": "echo default-ran", "exit_code": 0}],
        "unclaimed": [],
        "config_changed": False,
    }


@pytest.mark.parametrize(
    "text",
    [
        None,
        "not = [valid toml",
        "gate = 5\n",
        "[gate]\nstatic_checks = []\n",
        '[gate]\ntest_command = "  "\n',
        "[gate]\ntest_command = 5\n",
        '[gate]\ntest_command = "true"\nsuites = "web"\n',
        '[gate]\ntest_command = "true"\n[gate.suites.web]\ncommand = "echo web-ran"\n',
        '[gate]\ntest_command = "true"\n[gate.suites.web]\ncommand = "echo web-ran"\npaths = ["wbe/"]\n',
    ],
    ids=["missing", "bad toml", "gate not a table", "no test_command", "blank test_command",
         "test_command not text", "suites not a table", "suite without paths", "path that does not exist"],
)
def test_a_bad_config_exits_2_without_running_anything(repo, text):
    config = repo / "gate.toml"
    if text is not None:
        config.write_text(text)
    base = git(repo, "rev-parse", "HEAD")

    completed = config_command_line(repo, config, base)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr.startswith("gate_routes: ")
    assert str(config) in completed.stderr


def test_the_command_line_takes_the_gate_from_stdin_or_a_config_but_not_both(repo, configured):
    base = git(repo, "rev-parse", "HEAD")

    completed = subprocess.run(
        [sys.executable, str(STUDIO_ROOT / "gate_routes.py"), "--gate", "-", "--config", str(configured), "--base", base],
        cwd=str(repo), input=json.dumps(gate_input()), capture_output=True, text=True,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""

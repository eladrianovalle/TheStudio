from __future__ import annotations

import copy
import json
import os
import shlex
import subprocess
import sys
import types
from pathlib import Path

import pytest

import install
import packs
import run_phase
from install import install_studio
from packs import Department, binary_asset_problems, load_pack, report_problems, shipped_pack_names

STUDIO_DIR = Path(__file__).resolve().parents[1]
RUN_PHASE = STUDIO_DIR / "run_phase.py"
GAME_DOC = STUDIO_DIR / "packs" / "game" / "ASSET_PIPELINE.md"

CLEAN_ANIMATION = {
    "id": "x",
    "kind": "animation",
    "route": "code-built",
    "metrics": {
        "foot_slide": {"value": 0.8, "max": 1.0},
        "loop_seam": {"value": 0, "max": 0},
        "below_floor": {"value": 0.0, "max": 0.01},
        "stretch": {"value": 1.02, "min": 0.98, "max": 1.05},
    },
}
CLEAN_REPORT = {"assets": [CLEAN_ANIMATION]}


def game_art(routes: list[str] | None = None) -> Department:
    return Department(load_pack("game"), "art", "unused", routes or ["code-built"])


def animation(**changes) -> dict:
    asset = copy.deepcopy(CLEAN_ANIMATION)
    asset.update(changes)
    return asset


def with_metric(name: str, measurement: object) -> dict:
    asset = animation()
    asset["metrics"][name] = measurement
    return asset


@pytest.fixture(autouse=True)
def isolated_git(tmp_path, monkeypatch):
    empty_config = tmp_path / "empty.gitconfig"
    empty_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "game"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.org")
    git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("a game\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root


def commit(repo: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fixture")


def report_command(tmp_path: Path, report: object, before: str = "", after: str = "") -> str:
    report_file = tmp_path / "report.json"
    report_file.write_text(json.dumps(report))
    parts = [part for part in (before, f"cat {shlex.quote(str(report_file))}", after) if part]
    return "; ".join(parts)


def write_config(tmp_path: Path, asset_command: str, routes: list[str] | None = None) -> Path:
    config = tmp_path / "implementation_loop.toml"
    config.write_text(
        "[packs.game.art]\n"
        f"asset_command = {json.dumps(asset_command)}\n"
        f"routes = {json.dumps(routes or ['code-built'])}\n"
    )
    return config


def check_packs(repo: Path, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUN_PHASE), "check-packs", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def run_declared(repo: Path, tmp_path: Path, asset_command: str, routes: list[str] | None = None):
    config = write_config(tmp_path, asset_command, routes)
    return check_packs(repo, "--config", str(config))


def saved_result(repo: Path) -> dict:
    git_dir = Path(git(repo, "rev-parse", "--absolute-git-dir").strip())
    return json.loads((git_dir / "studio" / "pack-reports" / "game-art.json").read_text())


def test_the_game_pack_declares_mesh_and_animation_only():
    kinds = load_pack("game")["departments"]["art"]["kinds"]
    assert sorted(kinds) == ["animation", "mesh"]
    assert kinds["mesh"] == ["triangles", "part_gap", "extent"]
    assert kinds["animation"] == ["foot_slide", "loop_seam", "below_floor", "stretch"]


SPEC = STUDIO_DIR.parent / "specs" / "pack-mechanism.md"


def quoted_lines(text: str) -> str:
    return " ".join(line[2:].strip() for line in text.splitlines() if line.startswith("> "))


def test_the_game_doc_states_the_verdict_limit_word_for_word_from_the_spec():
    spec_limit = quoted_lines(SPEC.read_text(encoding="utf-8"))
    assert spec_limit.startswith("Studio code runs `check-packs` only on the portable host")
    assert spec_limit.endswith("changes the editor makes are not re-checked.")
    assert quoted_lines(GAME_DOC.read_text(encoding="utf-8")) == spec_limit


def test_the_game_doc_says_the_asset_command_must_leave_the_working_tree_unchanged():
    doc = " ".join(GAME_DOC.read_text(encoding="utf-8").split())
    assert "The asset command must leave the working tree unchanged" in doc


def test_studio_ships_the_game_pack():
    assert "game" in shipped_pack_names()


@pytest.mark.parametrize("pack_name", shipped_pack_names())
def test_every_shipped_pack_has_its_doc_a_metric_per_kind_and_a_binary_route_it_offers(pack_name):
    pack = load_pack(pack_name)
    assert pack["name"] == pack_name
    assert (STUDIO_DIR / "packs" / pack_name / pack["doc"]).is_file()
    assert pack["departments"]
    for department_name, department in pack["departments"].items():
        assert department["kinds"], department_name
        for kind, metrics in department["kinds"].items():
            assert metrics, f"{pack_name}.{department_name} kind {kind} has no metric"
        assert department["binary_assets"]["allowed_by_route"] in department["routes"]


def test_a_clean_report_has_no_problems():
    assert report_problems(CLEAN_REPORT, game_art()) == []


def test_an_empty_assets_list_has_no_problems():
    assert report_problems({"assets": []}, game_art()) == []


@pytest.mark.parametrize("report", [{}, {"assets": {}}, [], "assets", None])
def test_a_report_without_an_assets_list_fails(report):
    assert report_problems(report, game_art()) == ['the report needs an "assets" list']


def test_an_asset_without_an_id_is_named_by_its_position():
    report = {"assets": [animation(id="a"), animation(id="b"), animation(id=None)]}
    assert report_problems(report, game_art()) == ["asset #3 has no id"]


def test_a_repeated_id_fails_once():
    report = {"assets": [animation(), animation(), animation()]}
    assert report_problems(report, game_art()) == ['asset id "x" appears twice']


def test_an_unknown_kind_fails():
    report = {"assets": [animation(kind="texture", metrics={})]}
    assert report_problems(report, game_art()) == [
        'x: kind "texture" is not one the game pack knows (animation, mesh)'
    ]


def test_a_route_outside_the_repositorys_routes_fails():
    report = {"assets": [animation(route="hand-authored")]}
    assert report_problems(report, game_art()) == [
        "x: route \"hand-authored\" is not in this repository's routes (code-built)"
    ]


def test_a_missing_required_metric_fails():
    asset = animation()
    del asset["metrics"]["loop_seam"]
    assert report_problems({"assets": [asset]}, game_art()) == [
        "x: kind animation needs metric loop_seam, which the report does not have"
    ]


@pytest.mark.parametrize("measurement", [{"max": 1.0}, {"value": "0.8", "max": 1.0}, {"value": True, "max": 1.0}, 0.8])
def test_a_metric_without_a_numeric_value_fails(measurement):
    report = {"assets": [with_metric("foot_slide", measurement)]}
    assert report_problems(report, game_art()) == ["x: metric foot_slide has no numeric value"]


@pytest.mark.parametrize("measurement", [{"value": 0.8}, {"value": 0.8, "max": "1.0"}])
def test_a_metric_without_a_usable_limit_fails(measurement):
    report = {"assets": [with_metric("foot_slide", measurement)]}
    assert report_problems(report, game_art()) == ["x: metric foot_slide has no max or min"]


def test_a_min_above_its_max_fails():
    report = {"assets": [with_metric("foot_slide", {"value": 2, "min": 3, "max": 1})]}
    assert report_problems(report, game_art()) == ["x: metric foot_slide min 3 is above max 1"]


def test_metric_above_its_max_fails():
    report = {"assets": [with_metric("foot_slide", {"value": 1.4, "max": 1.0})]}
    assert report_problems(report, game_art()) == ["x: metric foot_slide is 1.4, above its max 1.0"]


def test_a_metric_below_its_min_fails():
    report = {"assets": [with_metric("stretch", {"value": 0.9, "min": 0.98, "max": 1.05})]}
    assert report_problems(report, game_art()) == ["x: metric stretch is 0.9, below its min 0.98"]


def test_a_metric_at_its_limit_passes():
    report = {"assets": [with_metric("stretch", {"value": 1.05, "min": 1.05, "max": 1.05})]}
    assert report_problems(report, game_art()) == []


def test_a_metric_beyond_the_required_ones_is_checked_the_same_way():
    report = {"assets": [with_metric("bone_count", {"value": 70, "max": 64})]}
    assert report_problems(report, game_art()) == ["x: metric bone_count is 70, above its max 64"]


def test_binary_assets_past_the_first_ten_are_counted():
    paths = [f"art/{number:02}.png" for number in range(12)]
    problems = binary_asset_problems(paths, load_pack("game")["departments"]["art"]["binary_assets"])
    assert len(problems) == 11
    assert problems[0] == "art/00.png is a binary asset git would commit, but no allowed route permits one (hand-authored)"
    assert problems[-1] == "and 2 more"


def test_a_clean_report_on_stdout_passes_and_is_saved(repo, tmp_path):
    command = report_command(tmp_path, CLEAN_REPORT)
    result = run_declared(repo, tmp_path, command)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == ["game.art: 1 assets within budget"]
    saved = saved_result(repo)
    assert saved["problems"] == []
    assert json.loads(saved["stdout"]) == CLEAN_REPORT


def test_saving_the_result_leaves_git_status_unchanged(repo, tmp_path):
    status_before = git(repo, "status", "--porcelain", "--untracked-files=all")
    run_declared(repo, tmp_path, report_command(tmp_path, CLEAN_REPORT))
    assert git(repo, "status", "--porcelain", "--untracked-files=all") == status_before


def test_an_empty_assets_list_passes_with_zero_assets(repo, tmp_path):
    result = run_declared(repo, tmp_path, report_command(tmp_path, {"assets": []}))
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["game.art: 0 assets"]


def test_only_stdout_is_read_as_the_report(repo, tmp_path):
    command = report_command(tmp_path, CLEAN_REPORT, before="echo 'Engine v4 starting' 1>&2")
    result = run_declared(repo, tmp_path, command)
    assert result.returncode == 0, result.stdout
    assert "Engine v4 starting" in result.stderr


def test_a_bad_report_exits_1_prints_each_problem_and_the_doc_and_saves_them(repo, tmp_path):
    report = {"assets": [with_metric("foot_slide", {"value": 1.4, "max": 1.0}), animation(id="y", route="generated")]}
    result = run_declared(repo, tmp_path, report_command(tmp_path, report))
    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "game.art: x: metric foot_slide is 1.4, above its max 1.0",
        "game.art: y: route \"generated\" is not in this repository's routes (code-built)",
        f"See {GAME_DOC}",
    ]
    assert saved_result(repo)["problems"] == [
        "x: metric foot_slide is 1.4, above its max 1.0",
        "y: route \"generated\" is not in this repository's routes (code-built)",
    ]


def test_output_that_is_not_json_fails_quoting_its_first_80_characters(repo, tmp_path):
    banner = "Godot Engine v4.2.1.stable.official - https://godotengine.org " + "x" * 60
    result = run_declared(repo, tmp_path, f"echo {shlex.quote(banner)}")
    assert result.returncode == 1
    first_line = result.stdout.splitlines()[0]
    assert first_line.startswith("game.art: the report is not valid JSON: Expecting value")
    assert first_line.endswith(f"; output began: {banner[:80]}")
    assert saved_result(repo)["problems"] == [first_line.removeprefix("game.art: ")]


def test_empty_output_fails_as_not_json(repo, tmp_path):
    result = run_declared(repo, tmp_path, "true")
    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == (
        "game.art: the report is not valid JSON: Expecting value: line 1 column 1 (char 0); output began: "
    )


def test_a_command_that_creates_a_file_fails_naming_it(repo, tmp_path):
    command = report_command(tmp_path, CLEAN_REPORT, before="echo cache > cache.txt")
    result = run_declared(repo, tmp_path, command)
    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == (
        "game.art: the asset command changed cache.txt; it must leave the working tree unchanged"
    )


def test_a_command_that_edits_a_clean_tracked_file_fails_naming_it(repo, tmp_path):
    command = report_command(tmp_path, CLEAN_REPORT, before="echo more >> README.md")
    result = run_declared(repo, tmp_path, command)
    assert result.returncode == 1
    assert "game.art: the asset command changed README.md; it must leave the working tree unchanged" in result.stdout


def test_a_command_that_appends_to_an_already_modified_tracked_file_fails_naming_it(repo, tmp_path):
    commit(repo, {"notes.txt": "first\n"})
    (repo / "notes.txt").write_text("the writer's change\n")
    command = report_command(tmp_path, CLEAN_REPORT, before="echo more >> notes.txt")
    result = run_declared(repo, tmp_path, command)
    assert result.returncode == 1
    assert "game.art: the asset command changed notes.txt; it must leave the working tree unchanged" in result.stdout


def test_a_command_that_rewrites_an_existing_untracked_file_fails_naming_it(repo, tmp_path):
    (repo / "draft.txt").write_text("the writer's new file\n")
    command = report_command(tmp_path, CLEAN_REPORT, before="echo rewritten > draft.txt")
    result = run_declared(repo, tmp_path, command)
    assert result.returncode == 1
    assert "game.art: the asset command changed draft.txt; it must leave the working tree unchanged" in result.stdout


def test_a_command_that_only_sets_the_executable_bit_on_a_modified_file_fails_naming_it(repo, tmp_path):
    commit(repo, {"tool.sh": "echo one\n"})
    (repo / "tool.sh").write_text("echo two\n")
    command = report_command(tmp_path, CLEAN_REPORT, before="chmod +x tool.sh")
    result = run_declared(repo, tmp_path, command)
    assert result.returncode == 1
    assert "game.art: the asset command changed tool.sh; it must leave the working tree unchanged" in result.stdout


def test_a_command_that_writes_only_under_an_ignored_path_passes(repo, tmp_path):
    commit(repo, {".gitignore": "build/\n", "notes.txt": "first\n"})
    (repo / "notes.txt").write_text("the writer's change\n")
    (repo / "draft.txt").write_text("the writer's new file\n")
    command = report_command(tmp_path, CLEAN_REPORT, before="mkdir -p build && echo cache > build/cache.txt")
    result = run_declared(repo, tmp_path, command)
    assert result.returncode == 0, result.stdout
    assert (repo / "build" / "cache.txt").is_file()


def test_a_clean_report_from_a_command_that_exits_non_zero_saves_the_exit_code(repo, tmp_path):
    command = report_command(tmp_path, CLEAN_REPORT, after="exit 3")
    result = run_declared(repo, tmp_path, command)
    assert result.returncode == 1
    assert result.stdout.splitlines() == [f"game.art: asset command exited 3: {command}", f"See {GAME_DOC}"]
    saved = saved_result(repo)
    assert saved["problems"] == [f"asset command exited 3: {command}"]
    assert json.loads(saved["stdout"]) == CLEAN_REPORT


def test_an_untracked_upper_case_png_fails_without_the_hand_authored_route(repo, tmp_path):
    (repo / "art").mkdir()
    (repo / "art" / "HERO.PNG").write_bytes(b"\x89PNG")
    result = run_declared(repo, tmp_path, report_command(tmp_path, CLEAN_REPORT))
    assert result.returncode == 1
    assert result.stdout.splitlines()[0] == (
        "game.art: art/HERO.PNG is a binary asset git would commit, but no allowed route permits one (hand-authored)"
    )
    assert saved_result(repo)["problems"] == [
        "art/HERO.PNG is a binary asset git would commit, but no allowed route permits one (hand-authored)"
    ]


def test_an_ignored_png_passes_without_the_hand_authored_route(repo, tmp_path):
    commit(repo, {".gitignore": "art/\n"})
    (repo / "art").mkdir()
    (repo / "art" / "HERO.PNG").write_bytes(b"\x89PNG")
    result = run_declared(repo, tmp_path, report_command(tmp_path, CLEAN_REPORT))
    assert result.returncode == 0, result.stdout


def test_a_tracked_png_deleted_in_the_worktree_passes_without_the_hand_authored_route(repo, tmp_path):
    commit(repo, {"art/hero.png": "png bytes"})
    (repo / "art" / "hero.png").unlink()
    result = run_declared(repo, tmp_path, report_command(tmp_path, CLEAN_REPORT))
    assert result.returncode == 0, result.stdout


def test_a_tracked_png_passes_when_the_hand_authored_route_is_allowed(repo, tmp_path):
    commit(repo, {"art/hero.png": "png bytes"})
    report = {"assets": [animation(route="hand-authored")]}
    result = run_declared(repo, tmp_path, report_command(tmp_path, report), routes=["code-built", "hand-authored"])
    assert result.returncode == 0, result.stdout


def test_the_repositorys_own_config_is_read_by_default(repo, tmp_path):
    config_dir = repo / ".studio"
    config_dir.mkdir()
    write_config(tmp_path, report_command(tmp_path, {"assets": []})).rename(config_dir / "implementation_loop.toml")
    subdirectory = repo / "src"
    subdirectory.mkdir()
    result = check_packs(subdirectory)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["game.art: 0 assets"]


def test_a_repository_that_declares_no_pack_passes(repo, tmp_path):
    config = tmp_path / "implementation_loop.toml"
    config.write_text('[gate]\ntest_command = "pytest"\n')
    result = check_packs(repo, "--config", str(config))
    assert result.returncode == 0
    assert not (Path(git(repo, "rev-parse", "--absolute-git-dir").strip()) / "studio").exists()


def test_a_repository_with_no_config_file_passes(repo):
    assert check_packs(repo).returncode == 0


def test_a_directory_outside_git_cannot_be_checked(tmp_path):
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    config = write_config(tmp_path, "true")
    result = check_packs(outside, "--config", str(config))
    assert result.returncode == 2
    assert "not inside a git work tree" in result.stderr


def test_a_missing_explicit_config_cannot_be_checked(repo, tmp_path):
    result = check_packs(repo, "--config", str(tmp_path / "nowhere.toml"))
    assert result.returncode == 2


@pytest.mark.parametrize(
    "table, complaint",
    [
        ('[packs.music.art]\nasset_command = "true"\nroutes = ["code-built"]\n', "[packs.music] names a pack Studio does not ship."),
        ('[packs.game.art]\nasset_command = "true"\nroutes = ["sculpted"]\n', 'route "sculpted" is not one of the game pack\'s routes'),
        ('[packs.game.art]\nroutes = ["code-built"]\n', "[packs.game.art] needs a non-empty asset_command."),
        ('[packs.game.art]\nasset_command = "true"\nroutes = []\n', "[packs.game.art] needs a non-empty routes list."),
        ('[packs.game.art]\nasset_command = "true"\nroutes = ["code-built"]\nuse = true\n', "has a key it does not take: use"),
        ('[packs.game.sound]\nasset_command = "true"\nroutes = ["code-built"]\n', "the game pack has no department sound (art)"),
        ("[packs.game]\n", "[packs.game.art] is missing"),
        ('packs = "game"\n', "[packs] must be a table."),
        ("[packs.game.art\n", "not valid TOML"),
    ],
)
def test_a_bad_packs_table_cannot_be_checked(repo, tmp_path, table, complaint):
    config = tmp_path / "implementation_loop.toml"
    config.write_text(table)
    result = check_packs(repo, "--config", str(config))
    assert result.returncode == 2
    assert complaint in result.stderr
    assert str(config) in result.stderr
    if "TOML" not in complaint:
        assert "Shipped packs: game." in result.stderr


def test_install_ships_the_module_and_both_pack_files(tmp_path):
    target = tmp_path / "installed"
    target.mkdir()
    install_studio(target, STUDIO_DIR, install_hook=False, install_finish_check=False)
    source = target / ".studio" / "source"
    assert (source / "packs.py").read_text() == (STUDIO_DIR / "packs.py").read_text()
    assert (source / "packs" / "game" / "pack.json").read_text() == (STUDIO_DIR / "packs" / "game" / "pack.json").read_text()
    assert (source / "packs" / "game" / "ASSET_PIPELINE.md").read_text() == GAME_DOC.read_text()


def test_the_installed_check_runs_and_names_the_installed_doc(tmp_path):
    target = tmp_path / "installed"
    target.mkdir()
    git(target, "init", "-q")
    install_studio(target, STUDIO_DIR, install_hook=False, install_finish_check=False)
    (target / ".studio" / "implementation_loop.toml").write_text(
        "[packs.game.art]\n"
        f"asset_command = {json.dumps(report_command(tmp_path, {'assets': [animation(route='generated')]}))}\n"
        'routes = ["code-built"]\n'
    )
    result = subprocess.run(
        [sys.executable, str(target / ".studio" / "source" / "run_phase.py"), "check-packs"],
        cwd=target,
        capture_output=True,
        text=True,
        env={**os.environ, "STUDIO_DEBUG": "1"},
    )
    assert result.returncode == 1, result.stderr
    assert result.stdout.splitlines()[-1] == "See .studio/source/packs/game/ASSET_PIPELINE.md"


def test_check_packs_runs_in_process(repo, tmp_path, capsys):
    config = write_config(tmp_path, report_command(tmp_path, CLEAN_REPORT))
    assert packs.check_packs(config, cwd=repo) == 0
    assert capsys.readouterr().out.splitlines() == ["game.art: 1 assets within budget"]


def test_the_output_of_a_command_that_exits_non_zero_is_not_judged(repo, tmp_path):
    result = run_declared(repo, tmp_path, "echo 'not a report'; exit 4")
    assert result.returncode == 1
    assert saved_result(repo)["problems"] == ["asset command exited 4: echo 'not a report'; exit 4"]


DOC_SENTENCE = f"This repository uses Studio's game pack. Read {GAME_DOC} before building or changing an asset."
OWED_SPEC = (
    "---\n"
    "feature: A Feature\n"
    "slug: a-feature\n"
    "status: approved\n"
    "verification_due:\n"
    "---\n\n"
    "# A Feature\n\n"
    "## Build Plan\n\n"
    "### 1. `still_owed` — the one nobody built\n"
)


def declare(repo: Path, text: str) -> Path:
    config = repo / ".studio" / "implementation_loop.toml"
    config.parent.mkdir(exist_ok=True)
    config.write_text(text)
    return config


def declare_game_art(repo: Path, asset_command: str) -> Path:
    return declare(
        repo,
        "[packs.game.art]\n"
        f"asset_command = {json.dumps(asset_command)}\n"
        'routes = ["code-built"]\n',
    )


def saved_result_path(repo: Path) -> Path:
    git_dir = Path(git(repo, "rev-parse", "--absolute-git-dir").strip())
    return git_dir / "studio" / "pack-reports" / "game-art.json"


def save_problems(repo: Path, problems: list[str]) -> None:
    path = saved_result_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"problems": problems, "stdout": ""}))


def owe_a_unit(repo: Path) -> None:
    specs = repo / "specs"
    specs.mkdir()
    (specs / "a-feature.md").write_text(OWED_SPEC)


def announce_an_update(monkeypatch) -> None:
    monkeypatch.setattr(install, "compute_update_check", lambda *args, **kwargs: types.SimpleNamespace(should_notify=True))


def brief(repo: Path, capsys) -> str | None:
    run_phase._do_check_updates(types.SimpleNamespace(target=str(repo)))
    out = capsys.readouterr().out
    if not out.strip():
        return None
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


def check_updates(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUN_PHASE), "check-updates", "--target", str(repo)],
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("config", [None, "", '[gate]\ntest_command = "pytest"\n'])
def test_a_repository_without_packs_gets_no_brief(repo, capsys, config):
    if config is not None:
        declare(repo, config)
    assert brief(repo, capsys) is None


def test_a_repository_without_packs_gets_only_the_unfinished_work(repo, capsys):
    declare(repo, '[gate]\ntest_command = "pytest"\n')
    owe_a_unit(repo)
    assert brief(repo, capsys) == run_phase._unfinished_context(repo)


def test_a_declared_pack_with_no_saved_result_names_only_its_doc(repo, capsys):
    declare_game_art(repo, "true")
    context = brief(repo, capsys)
    assert context == DOC_SENTENCE
    assert GAME_DOC.is_file()


def test_a_clean_saved_result_adds_nothing_to_the_doc_line(repo, tmp_path, capsys):
    declare_game_art(repo, report_command(tmp_path, CLEAN_REPORT))
    assert check_packs(repo).returncode == 0
    assert json.loads(saved_result_path(repo).read_text())["problems"] == []
    assert brief(repo, capsys) == DOC_SENTENCE


def test_an_installed_repository_is_handed_a_doc_path_that_opens_from_its_root(tmp_path):
    target = tmp_path / "installed"
    target.mkdir()
    git(target, "init", "-q")
    install_studio(target, STUDIO_DIR, install_hook=False, install_finish_check=False)
    (target / ".studio" / install.UPDATE_CHECK_SENTINEL).write_text("")
    declare_game_art(target, "true")
    result = subprocess.run(
        [sys.executable, str(target / ".studio" / "source" / "run_phase.py"), "check-updates", "--target", str(target)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    doc = ".studio/source/packs/game/ASSET_PIPELINE.md"
    assert context == f"This repository uses Studio's game pack. Read {doc} before building or changing an asset."
    assert (target / doc).is_file()


def test_saved_problems_add_their_count_and_the_first_one(repo, tmp_path, capsys):
    report = {"assets": [animation(id="hero_walk", route="generated"), animation(id="hero_run", route="generated")]}
    declare_game_art(repo, report_command(tmp_path, report))
    assert check_packs(repo).returncode == 1
    context = brief(repo, capsys)
    assert context == (
        f"{DOC_SENTENCE} 2 pack problems; first: game.art: hero_walk: route \"generated\" is not in this "
        "repository's routes (code-built)."
    )


def test_a_command_that_exited_non_zero_is_reported_in_the_brief(repo, tmp_path, capsys):
    command = report_command(tmp_path, CLEAN_REPORT, after="exit 3")
    declare_game_art(repo, command)
    assert check_packs(repo).returncode == 1
    context = brief(repo, capsys)
    assert context == f"{DOC_SENTENCE} 1 pack problem; first: game.art: asset command exited 3: {command}."


@pytest.mark.parametrize(
    "table, complaint",
    [
        ('[packs.music.art]\nasset_command = "true"\nroutes = ["code-built"]\n', "[packs.music] names a pack Studio does not ship. Shipped packs: game."),
        ('[packs.game.art]\nroutes = ["code-built"]\n', "[packs.game.art] needs a non-empty asset_command. Shipped packs: game."),
    ],
)
def test_a_malformed_packs_table_adds_its_count_and_its_problem(repo, capsys, table, complaint):
    config = declare(repo, table)
    context = brief(repo, capsys)
    assert context == f"1 pack problem; first: {config}: {complaint.rstrip('.')}."


def test_a_packs_table_that_is_not_toml_adds_its_count_and_its_problem(repo, capsys):
    config = declare(repo, "[packs.game.art\n")
    context = brief(repo, capsys)
    assert context.startswith(f"1 pack problem; first: {config}: not valid TOML: ")


def test_a_malformed_packs_table_keeps_the_update_notice_and_the_unfinished_work(repo, monkeypatch, capsys):
    announce_an_update(monkeypatch)
    owe_a_unit(repo)
    config = declare(repo, '[packs.music.art]\nasset_command = "true"\nroutes = ["code-built"]\n')
    blocks = brief(repo, capsys).split("\n\n")
    assert blocks[0] == install.UPDATE_ADDITIONAL_CONTEXT
    assert blocks[1] == run_phase._unfinished_context(repo)
    assert blocks[2].startswith(f"1 pack problem; first: {config}: [packs.music]")
    assert len(blocks) == 3


def test_check_updates_exits_zero_with_a_malformed_packs_table(repo):
    owe_a_unit(repo)
    declare(repo, "[packs.game.art\n")
    result = check_updates(repo)
    assert result.returncode == 0, result.stderr
    blocks = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"].split("\n\n")
    assert blocks[0].startswith("Unfinished work:")
    assert blocks[1].startswith("1 pack problem; first: ")


@pytest.mark.parametrize(
    "saved",
    [b"not json", b'{"problems": "oops"}', b"[]", b"\xff\xfe\x00", b'{"problems": [3, null]}'],
)
def test_a_malformed_saved_result_keeps_every_other_sentence(repo, monkeypatch, capsys, saved):
    announce_an_update(monkeypatch)
    owe_a_unit(repo)
    declare_game_art(repo, "true")
    path = saved_result_path(repo)
    path.parent.mkdir(parents=True)
    path.write_bytes(saved)
    blocks = brief(repo, capsys).split("\n\n")
    assert blocks == [install.UPDATE_ADDITIONAL_CONTEXT, run_phase._unfinished_context(repo), DOC_SENTENCE]
    result = check_updates(repo)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"].endswith(DOC_SENTENCE)


def test_a_session_note_that_raises_keeps_the_update_notice_and_the_unfinished_work(repo, monkeypatch, capsys):
    announce_an_update(monkeypatch)
    owe_a_unit(repo)
    declare_game_art(repo, "true")

    def explode(target):
        raise RuntimeError("the pack note fell over")

    monkeypatch.setattr(packs, "session_note", explode)
    blocks = brief(repo, capsys).split("\n\n")
    assert blocks == [install.UPDATE_ADDITIONAL_CONTEXT, run_phase._unfinished_context(repo)]


def test_the_session_note_runs_no_command_but_git_rev_parse(repo, monkeypatch):
    marker = repo.parent / "asset-command-ran"
    declare_game_art(repo, f"touch {shlex.quote(str(marker))}")
    save_problems(repo, ["asset command exited 3: touch"])
    commands = []
    real_popen = subprocess.Popen

    def recording_popen(arguments, *rest, **options):
        commands.append(arguments)
        return real_popen(arguments, *rest, **options)

    monkeypatch.setattr(subprocess, "Popen", recording_popen)
    note = packs.session_note(repo)
    assert note == f"{DOC_SENTENCE} 1 pack problem; first: game.art: asset command exited 3: touch."
    assert commands == [["git", "rev-parse", "--absolute-git-dir"]]
    assert not marker.exists()


def test_a_git_that_does_not_answer_in_five_seconds_still_names_the_doc(repo, monkeypatch):
    declare_game_art(repo, "true")
    save_problems(repo, ["asset command exited 3: true"])
    timeouts = []

    def hung_git(arguments, **options):
        timeouts.append(options.get("timeout"))
        raise subprocess.TimeoutExpired(arguments, options.get("timeout"))

    monkeypatch.setattr(subprocess, "run", hung_git)
    assert packs.session_note(repo) == DOC_SENTENCE
    assert timeouts == [5]

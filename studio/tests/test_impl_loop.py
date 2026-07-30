#!/usr/bin/env python3
"""Tests for the implementation writer/editor loop config loader."""
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from impl_loop import (
    LoopConfig,
    STUDIO_ROOT,
    VALID_MANDATES,
    VALID_READ_SCOPES,
    WORK_DIR_DIFFERENT_REPO,
    WORK_DIR_MISSING,
    WORK_DIR_NOT_A_WORKTREE,
    WorkDirError,
    _cli,
    _git_common_dir,
    load_loop_config,
    runtime_knobs,
    validate_work_dir,
)


def _write_toml(text: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(text)
        return Path(f.name)


def test_loop_config_defaults_match_spec():
    """A bare LoopConfig carries the shipped defaults from spec §4."""
    config = LoopConfig()
    assert config.deliver_on_gate_fail is True
    assert config.test_command == "pytest -q"
    assert config.static_checks == ["ruff"]
    assert config.require_mutation_check is True
    assert config.mutation_command == "mutmut run"
    assert config.mandate == "contrarian"
    assert config.read_scope == "touched+importers"
    assert config.output_budget == 400
    assert config.editor_enabled is True


def test_loop_config_off_mandate_disables_editor():
    """mandate = 'off' disables the editor pass."""
    config = LoopConfig(mandate="off")
    assert config.editor_enabled is False


def test_loop_config_invalid_mandate():
    """LoopConfig rejects an unknown mandate."""
    with pytest.raises(ValueError, match="mandate"):
        LoopConfig(mandate="bogus")
    assert "contrarian" in VALID_MANDATES
    assert "off" in VALID_MANDATES


def test_loop_config_invalid_output_budget_type():
    """output_budget must be an integer (and not a bool)."""
    with pytest.raises(ValueError, match="output_budget"):
        LoopConfig(output_budget="lots")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="output_budget"):
        LoopConfig(output_budget=True)  # type: ignore[arg-type]


def test_loop_config_invalid_static_checks_type():
    """static_checks must be a list."""
    with pytest.raises(ValueError, match="static_checks"):
        LoopConfig(static_checks="ruff")  # type: ignore[arg-type]


def test_loop_config_invalid_mutation_command_type():
    """mutation_command must be a string."""
    with pytest.raises(ValueError, match="mutation_command"):
        LoopConfig(mutation_command=["mutmut"])  # type: ignore[arg-type]


def test_loop_config_invalid_read_scope():
    """read_scope must be one of the known values, not an arbitrary string."""
    with pytest.raises(ValueError, match="read_scope"):
        LoopConfig(read_scope="everything")
    assert "touched+importers" in VALID_READ_SCOPES


def test_loop_config_invalid_bool_fields():
    """The boolean knobs reject non-bool values (e.g. a stray TOML string)."""
    with pytest.raises(ValueError, match="deliver_on_gate_fail"):
        LoopConfig(deliver_on_gate_fail="yes")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="require_mutation_check"):
        LoopConfig(require_mutation_check="no")  # type: ignore[arg-type]


def test_load_loop_config_valid():
    """A valid TOML file parses into a LoopConfig."""
    config_path = _write_toml("""
[loop]
deliver_on_gate_fail = false

[gate]
test_command = "python -m pytest tests/ -q"
static_checks = ["ruff", "mypy"]
require_mutation_check = false

[editor]
mandate = "off"
read_scope = "touched"
output_budget = 250
""")
    try:
        config = load_loop_config(config_path)
        assert config.deliver_on_gate_fail is False
        assert config.test_command == "python -m pytest tests/ -q"
        assert config.static_checks == ["ruff", "mypy"]
        assert config.require_mutation_check is False
        assert config.mandate == "off"
        assert config.read_scope == "touched"
        assert config.output_budget == 250
    finally:
        config_path.unlink()


def test_load_loop_config_partial_inherits_defaults():
    """Unspecified keys inherit the shipped defaults (shallow merge)."""
    config_path = _write_toml("""
[editor]
output_budget = 999
""")
    try:
        config = load_loop_config(config_path)
        # Overridden
        assert config.output_budget == 999
        # Inherited defaults
        assert config.test_command == "pytest -q"
        assert config.static_checks == ["ruff"]
        assert config.mandate == "contrarian"
        assert config.deliver_on_gate_fail is True
    finally:
        config_path.unlink()


def test_load_loop_config_explicit_missing_path_raises():
    """An explicit path that doesn't exist is an error (a typo), not a silent default.

    End-of-chain absence still yields defaults — see the no_config_anywhere test below.
    """
    with pytest.raises(FileNotFoundError):
        load_loop_config(Path("/nonexistent/implementation_loop.toml"))


def test_load_loop_config_no_config_anywhere_returns_defaults():
    """When the resolution chain finds nothing, defaults are returned."""
    with tempfile.TemporaryDirectory() as tmp:
        # Empty studio_root: no .studio/ and no config/ files exist.
        config = load_loop_config(studio_root=Path(tmp))
        assert config == LoopConfig()


def test_load_loop_config_invalid_toml():
    """Malformed TOML raises a clear ValueError."""
    config_path = _write_toml("invalid toml [[[")
    try:
        with pytest.raises(ValueError, match="Invalid TOML"):
            load_loop_config(config_path)
    finally:
        config_path.unlink()


def test_load_loop_config_studio_override_beats_shipped_default():
    """.studio/implementation_loop.toml wins over config/implementation_loop.toml."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".studio").mkdir()
        (root / "config").mkdir()
        (root / "config" / "implementation_loop.toml").write_text(
            '[editor]\noutput_budget = 400\n'
        )
        (root / ".studio" / "implementation_loop.toml").write_text(
            '[editor]\noutput_budget = 123\n'
        )
        config = load_loop_config(studio_root=root)
        assert config.output_budget == 123


def test_load_loop_config_installed_override_resolves_at_repo_root(tmp_path, monkeypatch):
    """In an installed layout (studio_root = <repo>/.studio/source), the project override
    is read from <repo>/.studio/, NOT from under the source snapshot."""
    monkeypatch.delenv("STUDIO_ARTIFACT_ROOT", raising=False)
    repo = tmp_path / "repo"
    snapshot = repo / ".studio" / "source"
    (snapshot / "config").mkdir(parents=True)
    # shipped default under the snapshot
    (snapshot / "config" / "implementation_loop.toml").write_text(
        "[editor]\noutput_budget = 400\n"
    )
    # project override at the REPO ROOT .studio/ (where the wizard writes it)
    (repo / ".studio" / "implementation_loop.toml").write_text(
        "[editor]\noutput_budget = 42\n"
    )
    config = load_loop_config(studio_root=snapshot)
    assert config.output_budget == 42  # override wins; before the fix this returned 400


def test_load_loop_config_artifact_root_env_override(tmp_path, monkeypatch):
    """STUDIO_ARTIFACT_ROOT points the project-override lookup at an explicit root."""
    repo = tmp_path / "elsewhere"
    (repo / ".studio").mkdir(parents=True)
    (repo / ".studio" / "implementation_loop.toml").write_text("[editor]\nmandate = \"off\"\n")
    snapshot = tmp_path / "src" / ".studio" / "source"
    snapshot.mkdir(parents=True)
    monkeypatch.setenv("STUDIO_ARTIFACT_ROOT", str(repo))
    config = load_loop_config(studio_root=snapshot)
    assert config.mandate == "off"


def test_load_loop_config_falls_back_to_shipped_default():
    """With no .studio override, the shipped config/ default is used."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "config").mkdir()
        (root / "config" / "implementation_loop.toml").write_text(
            '[editor]\nmandate = "off"\n'
        )
        config = load_loop_config(studio_root=root)
        assert config.mandate == "off"


def test_explicit_path_beats_resolution_chain():
    """An explicit path takes priority over the .studio/config chain."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".studio").mkdir()
        (root / ".studio" / "implementation_loop.toml").write_text(
            '[editor]\noutput_budget = 50\n'
        )
        explicit = _write_toml('[editor]\noutput_budget = 777\n')
        try:
            config = load_loop_config(explicit, studio_root=root)
            assert config.output_budget == 777
        finally:
            explicit.unlink()


def test_runtime_knobs_default_config():
    """runtime_knobs maps a default LoopConfig to the expected knob dict."""
    knobs = runtime_knobs(LoopConfig())
    assert knobs == {
        "editor_enabled": True,
        "test_command": "pytest -q",
        "static_checks": ["ruff"],
        "require_mutation_check": True,
        "mutation_command": "mutmut run",
        "read_scope": "touched+importers",
        "output_budget": 400,
    }


def test_runtime_knobs_reflects_loaded_override():
    """Values from a loaded .studio override flow through to the knobs."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".studio").mkdir()
        (root / ".studio" / "implementation_loop.toml").write_text(
            "[gate]\n"
            'test_command = "python -m pytest tests/ -q"\n'
            'static_checks = ["ruff", "mypy"]\n'
            "require_mutation_check = false\n"
            "[editor]\n"
            'mandate = "off"\n'
            'read_scope = "touched"\n'
            "output_budget = 250\n"
        )
        config = load_loop_config(studio_root=root)
        knobs = runtime_knobs(config)
        assert knobs == {
            "editor_enabled": False,
            "test_command": "python -m pytest tests/ -q",
            "static_checks": ["ruff", "mypy"],
            "require_mutation_check": False,
            "mutation_command": "mutmut run",
            "read_scope": "touched",
            "output_budget": 250,
        }


def test_load_default_loop_config():
    """The shipped default implementation_loop.toml loads correctly."""
    default_path = Path(__file__).resolve().parents[1] / "config" / "implementation_loop.toml"
    if not default_path.exists():
        pytest.skip("Default implementation_loop.toml not found")

    config = load_loop_config(default_path)
    assert config.deliver_on_gate_fail is True
    assert config.test_command == "pytest -q"
    assert config.static_checks == ["ruff"]
    assert config.require_mutation_check is True
    assert config.mutation_command == "mutmut run"
    assert config.mandate == "contrarian"
    assert config.read_scope == "touched+importers"
    assert config.output_budget == 400


def test_cli_no_arg_emits_default_knobs():
    """`impl_loop.py` with no arg prints the default runtime knobs as JSON."""
    knobs = json.loads(_cli(["impl_loop.py"]))
    assert knobs["editor_enabled"] is True
    assert knobs["read_scope"] == "touched+importers"
    assert knobs["output_budget"] == 400


def test_cli_explicit_path_reflects_override():
    """An explicit config path arg flows into the emitted knobs.

    This is how /forge passes an installed repo's project override
    (`.studio/implementation_loop.toml`), which lives outside the snapshot chain.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "implementation_loop.toml"
        cfg.write_text('[editor]\nmandate = "off"\noutput_budget = 99\n')
        knobs = json.loads(_cli(["impl_loop.py", str(cfg)]))
        assert knobs["editor_enabled"] is False
        assert knobs["output_budget"] == 99


def test_cli_explicit_missing_path_raises():
    """A typo'd explicit config path is loud, not silently defaulted."""
    with pytest.raises(FileNotFoundError):
        _cli(["impl_loop.py", "/nonexistent/implementation_loop.toml"])


# --- --work-dir validation -------------------------------------------------
#
# These use real `git init` / `git worktree add` rather than mocked subprocess calls.
# The whole point of the check is that git's plumbing answers the way we think it
# does, and a mock would only prove we can repeat our own assumptions back to us.


def _git(directory: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(directory), check=True, capture_output=True)


def _make_repo(root: Path) -> Path:
    """A git repository with one commit, so worktrees can be added to it."""
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "commit", "-q", "--allow-empty", "-m", "init")
    return root


def _add_worktree(repo: Path, path: Path, branch: str) -> Path:
    _git(repo, "worktree", "add", "-q", "-b", branch, str(path))
    return path


def test_validate_work_dir_accepts_a_worktree_of_this_repo(tmp_path):
    """The happy path: a real worktree of the main repo hands back its resolved path."""
    repo = _make_repo(tmp_path / "repo")
    worktree = _add_worktree(repo, tmp_path / "wt", "feature")
    assert validate_work_dir(worktree, main_repo=repo) == worktree.resolve()


def test_validate_work_dir_rejects_a_path_that_does_not_exist(tmp_path):
    """Criterion 1: a path that isn't there names the 'missing' reason and the path."""
    absent = tmp_path / "not-here"
    with pytest.raises(WorkDirError) as refused:
        validate_work_dir(absent, main_repo=tmp_path)
    assert WORK_DIR_MISSING in str(refused.value)
    assert str(absent.resolve()) in str(refused.value)


def test_validate_work_dir_rejects_a_directory_that_is_not_a_worktree(tmp_path):
    """Criterion 2: an ordinary directory names the 'not-a-worktree' reason."""
    repo = _make_repo(tmp_path / "repo")
    plain = tmp_path / "just-a-folder"
    plain.mkdir()
    with pytest.raises(WorkDirError) as refused:
        validate_work_dir(plain, main_repo=repo)
    assert WORK_DIR_NOT_A_WORKTREE in str(refused.value)
    assert str(plain.resolve()) in str(refused.value)


def test_validate_work_dir_rejects_a_worktree_of_another_repository(tmp_path):
    """Criterion 3: a genuine worktree of some OTHER repo names 'different-repo'.

    This is the case a bare `is this a worktree?` check would wave through, and it is
    the one that quietly builds the unit in the wrong project.
    """
    ours = _make_repo(tmp_path / "ours")
    theirs = _make_repo(tmp_path / "theirs")
    stranger = _add_worktree(theirs, tmp_path / "their-wt", "feature")
    with pytest.raises(WorkDirError) as refused:
        validate_work_dir(stranger, main_repo=ours)
    assert WORK_DIR_DIFFERENT_REPO in str(refused.value)
    assert str(stranger.resolve()) in str(refused.value)


def test_git_common_dir_uses_the_absolute_path_format(tmp_path):
    """Criterion 4: the same-repo check only works because of --path-format=absolute.

    Drop that flag and git answers the main checkout with a bare relative `.git`, which
    resolves against whatever directory the caller happens to be sitting in — never the
    repo it asked about. Verified by removing the flag: this test and the happy-path
    test above both go red, and the reported path is the caller's own tree.
    """
    repo = _make_repo(tmp_path / "repo")
    worktree = _add_worktree(repo, tmp_path / "wt", "feature")
    shared_git_dir = str((repo / ".git").resolve())

    from_main = _git_common_dir(repo)
    from_worktree = _git_common_dir(worktree)

    assert from_main == shared_git_dir
    # A worktree and its main repo share one common dir. (--git-dir would differ here:
    # the worktree's is <common>/worktrees/<name>.)
    assert from_worktree == shared_git_dir


def test_git_common_dir_is_none_outside_a_repository(tmp_path):
    """Not-a-worktree is signalled by None, which is what separates reason 2 from 3."""
    plain = tmp_path / "plain"
    plain.mkdir()
    assert _git_common_dir(plain) is None


def test_cli_work_dir_flag_reports_the_resolved_path():
    """A good --work-dir flows into the knobs JSON as an absolute path.

    That resolved path is what /forge pins scriptPath and its git commands to, so the
    CLI hands back the resolved form rather than whatever the user typed. Studio's own
    checkout stands in for the work dir here: the CLI compares against this repo, so
    only a directory in this repo can pass.
    """
    knobs = json.loads(_cli(["impl_loop.py", "--work-dir", str(STUDIO_ROOT)]))
    assert knobs["work_dir"] == str(STUDIO_ROOT)
    assert knobs["editor_enabled"] is True


def test_cli_bad_work_dir_raises_before_any_knobs_are_emitted(tmp_path):
    """A bad --work-dir stops the run: the CLI raises instead of printing knobs.

    /forge runs this before it invokes the workflow, so nothing spawns.
    """
    absent = tmp_path / "not-here"
    with pytest.raises(WorkDirError, match=WORK_DIR_MISSING):
        _cli(["impl_loop.py", "--work-dir", str(absent)])

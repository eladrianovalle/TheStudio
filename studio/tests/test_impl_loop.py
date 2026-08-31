#!/usr/bin/env python3
"""Tests for the implementation writer/editor loop config loader."""
import dataclasses
import json
import os
import string
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from config_loading import tomllib
from impl_loop import (
    LoopConfig,
    LoopConfigError,
    PROFILES,
    STACK_MARKERS,
    STUDIO_ROOT,
    VALID_MANDATES,
    VALID_READ_SCOPES,
    WORK_DIR_DIFFERENT_REPO,
    WORK_DIR_MISSING,
    WORK_DIR_NOT_A_WORKTREE,
    WorkDirError,
    WORK_DIR_UNQUOTABLE,
    _ALLOWED,
    _ALLOWED_SUMMARY,
    _KNOWN_BAD,
    _cli,
    _git_common_dir,
    detect_stacks,
    explain_unquotable_path,
    load_loop_config,
    resolve_profile,
    runtime_knobs,
    validate_work_dir,
)


@pytest.fixture(autouse=True)
def _ignore_ambient_artifact_root(monkeypatch):
    """Keep a STUDIO_ARTIFACT_ROOT in the developer's shell out of these tests.

    The gate commands are detected from whichever repo the loader resolves to, and that
    variable moves it. Without this, a machine that happens to export it would run every
    fixture's detection against an unrelated directory. The one test that is *about* the
    variable sets it back for itself.
    """
    monkeypatch.delenv("STUDIO_ARTIFACT_ROOT", raising=False)


def _write_toml(text: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(text)
        return Path(f.name)


def _python_repo(root: Path) -> Path:
    """Make ``root`` look like a Python project, and hand it back.

    The loader now refuses a repository whose stack it cannot identify, so a fixture that
    only cares about the config resolution chain still has to look like *something*.
    Python is the cheapest one to write, and it keeps these tests asserting what they
    always asserted.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text('[project]\nname = "fixture"\n')
    return root


def _node_repo(root: Path, package: dict) -> Path:
    """A repository whose only marker is a package.json holding ``package``."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(json.dumps(package))
    return root


def test_loop_config_defaults_match_spec():
    """A bare LoopConfig carries the shipped defaults from spec §4."""
    config = LoopConfig()
    assert config.deliver_on_gate_fail is True
    assert config.test_command == "pytest -q"
    assert config.static_checks == ["ruff check {paths}"]
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
static_checks = ["ruff check {paths}", "mypy {paths}"]
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
        assert config.static_checks == ["ruff check {paths}", "mypy {paths}"]
        assert config.require_mutation_check is False
        assert config.mandate == "off"
        assert config.read_scope == "touched"
        assert config.output_budget == 250
    finally:
        config_path.unlink()


def test_load_loop_config_partial_inherits_defaults():
    """Unspecified keys inherit the defaults (shallow merge).

    The gate half of those defaults is detected from this repo, which is a Python
    project — the stack-detected gate commands block below covers that on its own.
    """
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
        assert config.static_checks == ["ruff check {paths}"]
        assert config.mandate == "contrarian"
        assert config.deliver_on_gate_fail is True
    finally:
        config_path.unlink()


def test_load_loop_config_explicit_missing_path_raises():
    """An explicit path that doesn't exist is an error (a typo), not a silent default.

    End-of-chain absence is a different failure — see the no_config_and_no_stack test
    below, which refuses rather than raising FileNotFoundError.
    """
    with pytest.raises(FileNotFoundError):
        load_loop_config(Path("/nonexistent/implementation_loop.toml"))


def test_load_loop_config_no_config_and_no_stack_refuses():
    """A repo Studio can't identify is refused at load, not handed Python's commands.

    This reverses the contract this test used to state — absence used to yield the
    shipped defaults. Nine of the ten repos that run /forge are not Python projects, so
    that default meant `pytest` failing for a reason that had nothing to do with the
    unit. The refusal has to name the repo it looked in and the file to write, because
    for five of those repos it is the only thing they will see.
    """
    with tempfile.TemporaryDirectory() as tmp:
        # Empty studio_root: no marker files, no .studio/ and no config/ files exist.
        with pytest.raises(LoopConfigError) as excinfo:
            load_loop_config(studio_root=Path(tmp))

        message = str(excinfo.value)
        assert tmp in message
        assert ".studio/implementation_loop.toml" in message
        assert "Detected:   nothing" in message
        # No escape hatch: the only value that would satisfy one is a no-op command.
        assert "skip" not in message.lower()


def test_load_loop_config_invalid_toml():
    """Malformed TOML raises a clear ValueError."""
    config_path = _write_toml("invalid toml [[[")
    try:
        with pytest.raises(ValueError, match="Invalid TOML"):
            load_loop_config(config_path)
    finally:
        config_path.unlink()


@pytest.mark.parametrize("table", ["loop", "gate", "editor"])
def test_load_loop_config_non_table_value_names_the_table(table):
    """A scalar where a table belongs (`gate = "ruff"`) errors and names that table.

    Without the name the message points at the file and leaves you to work out which
    of the three sections is the wrong one.
    """
    config_path = _write_toml(f'{table} = "not a table"\n')
    try:
        with pytest.raises(ValueError, match=f"'{table}' must be a table/dict"):
            load_loop_config(config_path)
    finally:
        config_path.unlink()


def test_load_loop_config_plain_source_dir_is_not_an_installed_snapshot(tmp_path):
    """Only the full `<repo>/.studio/source` shape climbs to the repo root.

    A directory that merely happens to be named `source` reads its own `.studio/`, so
    an unrelated `.studio/` two levels up can never hijack the config.
    """
    source = _python_repo(tmp_path / "checkout" / "source")
    (source / ".studio").mkdir(parents=True)
    (source / ".studio" / "implementation_loop.toml").write_text(
        "[editor]\noutput_budget = 111\n"
    )
    # Decoy at the grandparent — where the installed-layout rule would have looked.
    (tmp_path / ".studio").mkdir()
    (tmp_path / ".studio" / "implementation_loop.toml").write_text(
        "[editor]\noutput_budget = 222\n"
    )

    assert load_loop_config(studio_root=source).output_budget == 111


def test_load_loop_config_studio_override_beats_shipped_default():
    """.studio/implementation_loop.toml wins over config/implementation_loop.toml."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _python_repo(Path(tmp))
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
    repo = _python_repo(tmp_path / "repo")
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
    repo = _python_repo(tmp_path / "elsewhere")
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
        root = _python_repo(Path(tmp))
        (root / "config").mkdir()
        (root / "config" / "implementation_loop.toml").write_text(
            '[editor]\nmandate = "off"\n'
        )
        config = load_loop_config(studio_root=root)
        assert config.mandate == "off"


def test_explicit_path_beats_resolution_chain():
    """An explicit path takes priority over the .studio/config chain."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _python_repo(Path(tmp))
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
        "static_checks": ["ruff check {paths}"],
        "require_mutation_check": True,
        "mutation_command": "mutmut run",
        "read_scope": "touched+importers",
        "output_budget": 400,
    }


def test_runtime_knobs_reflects_loaded_override():
    """Values from a loaded .studio override flow through to the knobs."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _python_repo(Path(tmp))
        (root / ".studio").mkdir()
        (root / ".studio" / "implementation_loop.toml").write_text(
            "[gate]\n"
            'test_command = "python -m pytest tests/ -q"\n'
            'static_checks = ["ruff check {paths}", "mypy {paths}"]\n'
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
            "static_checks": ["ruff check {paths}", "mypy {paths}"],
            "require_mutation_check": False,
            "mutation_command": "mutmut run",
            "read_scope": "touched",
            "output_budget": 250,
        }


SHIPPED_CONFIG = Path(__file__).resolve().parents[1] / "config" / "implementation_loop.toml"


def test_load_default_loop_config():
    """The shipped default implementation_loop.toml loads correctly.

    The gate half of this config is not in the file — it comes from detecting this
    repository, which is a Python project, so the values are the ones they always were.
    """
    if not SHIPPED_CONFIG.exists():
        pytest.skip("Default implementation_loop.toml not found")

    config = load_loop_config(SHIPPED_CONFIG)
    assert config.deliver_on_gate_fail is True
    assert config.test_command == "pytest -q"
    assert config.static_checks == ["ruff check {paths}"]
    assert config.require_mutation_check is True
    assert config.mutation_command == "mutmut run"
    assert config.mandate == "contrarian"
    assert config.read_scope == "touched+importers"
    assert config.output_budget == 400


def test_shipped_config_ships_no_gate_table():
    """The shipped file must define no [gate] table, or detection is dead code.

    Nine of the ten repos with Studio installed have no config file of their own, so the
    shipped one is what they resolve to. As long as it hard-sets the gate, it wins over
    everything detection computes and every one of those repos still runs `pytest`.
    """
    with open(SHIPPED_CONFIG, "rb") as f:
        data = tomllib.load(f)
    assert "gate" not in data


def test_shipped_config_matches_dataclass_defaults():
    """The shipped [loop]/[editor] values must equal LoopConfig()'s own defaults.

    A project file is read *instead of* the shipped one, so the moment a repo writes one
    these two tables are never read again and those keys fall back to the dataclass. The
    values are identical today, which is the only reason that shadowing is harmless. This
    test is what makes a future edit to either side fail loudly instead of going dark in
    every repo that has its own file.
    """
    with open(SHIPPED_CONFIG, "rb") as f:
        data = tomllib.load(f)
    defaults = LoopConfig()
    assert data["loop"]["deliver_on_gate_fail"] == defaults.deliver_on_gate_fail
    assert data["editor"]["mandate"] == defaults.mandate
    assert data["editor"]["read_scope"] == defaults.read_scope
    assert data["editor"]["output_budget"] == defaults.output_budget


def test_shipped_config_is_still_installed_into_consuming_repos():
    """The shipped config must stay in SOURCE_FILES even with its [gate] table gone.

    There is no prune for `.studio/source/`, so dropping the file from the install list
    would leave every already-installed repo holding its old copy — [gate] table intact —
    forever, which is the one outcome this whole change exists to prevent.
    """
    from install import SOURCE_FILES

    assert "config/implementation_loop.toml" in SOURCE_FILES


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


def test_validate_work_dir_rejects_a_path_that_would_break_the_quoting(tmp_path):
    """A path carrying a quote gets out of `git -C "<path>"` and runs as its own command.

    The loop renders that string into instruction text an agent then executes, so this
    is the one validation failure that is not merely inconvenient. Checked before the
    is_dir test on purpose: such a directory can genuinely exist.
    """
    hostile = tmp_path / 'wt"; echo pwned; #'
    hostile.mkdir()

    with pytest.raises(WorkDirError) as excinfo:
        validate_work_dir(hostile)

    message = str(excinfo.value)
    assert WORK_DIR_UNQUOTABLE in message
    # Explains the character it knows about, so the reader knows what to rename.
    reason = _KNOWN_BAD['"']
    assert "'\"' " + reason in message


def test_validate_work_dir_rejects_a_trailing_backslash(tmp_path):
    """A trailing backslash escapes the closing quote rather than ending the path.

    `.../wt\\` renders as `git -C ".../wt\\" add -A`, where the quote is escaped, so
    the shell never sees the boundary. It is a legal POSIX directory name, which is
    why it has to be refused by name rather than assumed away.
    """
    hostile = tmp_path / "wt\\"
    hostile.mkdir()

    with pytest.raises(WorkDirError) as excinfo:
        validate_work_dir(hostile)

    message = str(excinfo.value)
    assert WORK_DIR_UNQUOTABLE in message
    # Shown as the one character the user typed. repr() would print '\\' here, which
    # reads as two backslashes and matches nothing they can find in their own path.
    assert "'\\' " in message
    assert "'\\\\'" not in message


def test_validate_work_dir_rejects_a_character_no_one_wrote_down(tmp_path):
    """The point of an allowlist: refuse what nobody thought to ban.

    A semicolon separates commands just as effectively as a quote does, and it was
    never on the old banned list. Nothing explains it, because nothing has to — being
    outside the accepted set is the whole reason.
    """
    hostile = tmp_path / "wt;echo pwned"
    hostile.mkdir()

    with pytest.raises(WorkDirError) as excinfo:
        validate_work_dir(hostile)

    assert WORK_DIR_UNQUOTABLE in str(excinfo.value)
    assert ";" not in _KNOWN_BAD


def test_explain_unquotable_path_accepts_an_ordinary_path():
    """An everyday worktree path, spaces and a tilde included, raises nothing."""
    assert explain_unquotable_path("/Users/me/Repos/my project-1/.wt~") is None


def test_explain_unquotable_path_points_a_caret_at_each_offender():
    """The carets line up under the characters that have to go, and only those.

    Compared as whole lines rather than substrings: a caret sitting one column too
    far right still contains "spaces then a caret", so a loose check would pass on
    a message pointing at the wrong character.
    """
    lines = explain_unquotable_path("/a/b+c&d").splitlines()
    path_line = lines.index("    /a/b+c&d")

    assert lines[path_line + 1] == "        ^ ^"


def test_explain_unquotable_path_states_the_accepted_set_and_the_fix():
    """A refusal that doesn't say what is allowed leaves the reader guessing."""
    message = explain_unquotable_path("/a/b&c")

    assert _ALLOWED_SUMMARY in message
    assert "Rename the directory" in message


def test_known_bad_characters_are_already_refused_by_the_allowlist():
    """_KNOWN_BAD explains a refusal; it must never be the thing deciding one.

    If a key ever drifted into _ALLOWED, that character would be accepted while the
    code still carried a note about why it is dangerous.
    """
    assert not (set(_KNOWN_BAD) & _ALLOWED)


def test_the_accepted_set_prose_matches_the_allowlist():
    """The sentence users are shown is hand-written, so pin it to the real set.

    _ALLOWED_SUMMARY says "letters, digits, and any of / . _ - ~ or a space".
    """
    punctuation = _ALLOWED - set(string.ascii_letters + string.digits)
    assert punctuation == set("/._- ~")
    for character in punctuation - {" "}:
        assert character in _ALLOWED_SUMMARY
    assert "a space" in _ALLOWED_SUMMARY
    assert set(string.ascii_letters + string.digits) <= _ALLOWED


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


# --- stack-detected gate commands ------------------------------------------
#
# The gate's test command is detected from the repository being built in, not shipped.
# These fixtures are real directories holding real marker files: detection reads the
# filesystem, and a mocked one would only prove we can repeat our own assumptions back.


def _unity_repo(root: Path) -> Path:
    """A repository whose only marker is Unity's ProjectVersion.txt."""
    (root / "ProjectSettings").mkdir(parents=True)
    (root / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.0.0f1\n")
    return root


def _override(root: Path, text: str) -> Path:
    """Write a project override at ``root/.studio/implementation_loop.toml``."""
    (root / ".studio").mkdir(parents=True, exist_ok=True)
    (root / ".studio" / "implementation_loop.toml").write_text(text)
    return root


def test_node_repo_with_a_test_script_gets_npm_test(tmp_path):
    """A Node project resolves to `npm test`, and to no mutation gate.

    Three of the ten repos with Studio installed are Node projects, and every /forge run
    in them used to fail on a `pytest` that was never there. Mutation checking is off
    because no mutation tool is wired up for them: a gate that always passes with
    "unavailable" is decoration.
    """
    root = _node_repo(tmp_path, {"scripts": {"test": "vitest run", "lint": "eslint ."}})

    config = load_loop_config(studio_root=root)

    assert config.test_command == "npm test"
    assert config.require_mutation_check is False


@pytest.mark.parametrize("package, expected_checks", [
    ({"scripts": {"test": "node --test"}}, []),
    ({"scripts": {"test": "vitest run", "lint": "eslint ."}}, ["npm run lint"]),
    ({"scripts": {"test": "vitest run"}, "devDependencies": {"eslint": "^9.0.0"}}, ["npx eslint {paths}"]),
    # A lint script AND the dependency: the script is the repo's own answer, so it wins.
    (
        {
            "scripts": {"test": "vitest run", "lint": "biome check ."},
            "devDependencies": {"eslint": "^9.0.0"},
        },
        ["npm run lint"],
    ),
])
def test_node_static_check_follows_the_signs_of_a_linter(tmp_path, package, expected_checks):
    """The lint command comes from what package.json declares, and the two signs are told
    apart because they need different commands: a `lint` script runs through npm, eslint in
    devDependencies runs directly.

    An empty static_checks list means the writer skips the check, which is the honest
    answer for a package that declares neither.
    """
    root = _node_repo(tmp_path, package)

    assert load_loop_config(studio_root=root).static_checks == expected_checks


@pytest.mark.parametrize("lint_script", ["", "   ", "\t\n"])
def test_a_blank_lint_script_is_no_lint_script(tmp_path, lint_script):
    """`"lint": ""` runs nothing and exits 0, which would report a clean check having run
    nothing — the exact wrong-reason *pass* this detection exists to avoid.

    Membership alone ("lint" in scripts) was harmless while the list was only a flag. Now
    that the script becomes the command, a blank one has to fall through to the next sign.
    """
    package = {"scripts": {"test": "vitest run", "lint": lint_script}}
    package["devDependencies"] = {"eslint": "^9.0.0"}

    assert load_loop_config(studio_root=_node_repo(tmp_path, package)).static_checks == [
        "npx eslint {paths}"
    ]

    # And with nothing else to fall through to, a blank script means no static check at all.
    bare = {"scripts": {"test": "vitest run", "lint": lint_script}}
    assert load_loop_config(studio_root=_node_repo(tmp_path / "bare", bare)).static_checks == []


def test_python_repo_keeps_pytest_ruff_and_the_mutation_gate(tmp_path):
    """A Python project resolves to exactly the commands that used to be hard-coded."""
    root = _python_repo(tmp_path / "py")

    config = load_loop_config(studio_root=root)

    assert config.test_command == "pytest -q"
    assert config.static_checks == ["ruff check {paths}"]
    assert config.require_mutation_check is True
    assert config.mutation_command == "mutmut run"


@pytest.mark.parametrize("marker, contents", [
    ("pyproject.toml", '[project]\nname = "fixture"\n'),
    ("setup.py", "from setuptools import setup\n\nsetup()\n"),
    ("requirements.txt", "pytest\n"),
    ("conftest.py", "# fixtures live here\n"),
])
def test_any_one_python_marker_is_enough_on_its_own(tmp_path, marker, contents):
    """Every marker in the table is there for some repo, so each one is pinned here —
    an untested marker can be deleted by accident and nothing says so.

    conftest.py alone is _Cerebro's exact shape: without that marker it is undetectable,
    and a Python project would be refused a Python gate.
    """
    (tmp_path / marker).write_text(contents)

    assert load_loop_config(studio_root=tmp_path).test_command == "pytest -q"


def test_unity_override_inherits_nothing_from_python(tmp_path):
    """An override setting only test_command gets no Python value through the gap.

    This is the same bug one level down: before the merge base became the detected
    profile, a Unity repo naming only its test wrapper still inherited `ruff` and
    `mutmut` from the shipped defaults and failed the gate on tools it does not have.
    """
    root = _unity_repo(tmp_path)
    _override(root, '[gate]\ntest_command = "./scripts/run-editmode-tests.sh"\n')

    config = load_loop_config(studio_root=root)

    assert config.test_command == "./scripts/run-editmode-tests.sh"
    assert config.static_checks == []
    assert config.require_mutation_check is False


def test_orkid_gardens_own_override_still_resolves_and_raises_nothing(tmp_path):
    """The repo that reported this bug keeps working, byte-for-byte as it is today.

    Orkid Garden keeps its Unity project in a subdirectory, so nothing at its root
    identifies it — detection alone would refuse. Its hand-written override is still the
    answer, and this change must not disturb it.
    """
    root = tmp_path / "Orkid Garden"
    root.mkdir()
    (root / "unity").mkdir()  # the Unity project, invisible to root-only detection
    _override(root, (
        "# Orkid Garden's overrides for the implementation writer/editor loop.\n"
        "\n"
        "[gate]\n"
        'test_command = "./scripts/run-editmode-tests.sh"\n'
        "static_checks = []\n"
        "require_mutation_check = false\n"
    ))

    config = load_loop_config(studio_root=root)

    assert config.test_command == "./scripts/run-editmode-tests.sh"
    assert config.static_checks == []
    assert config.require_mutation_check is False


def test_alfreds_own_override_finally_runs_the_lint_it_always_named(tmp_path):
    """Alfred's config has held a lint *command* since before this field ran anything.

    It is the reason the field holds commands now rather than names: the file says
    `make lint`, and nothing has ever run it. This pins that the file loads untouched —
    the value reaches the loop as written, with no {paths} appended to it.
    """
    root = tmp_path / "_Alfred"
    root.mkdir()
    _override(root, (
        "[gate]\n"
        'test_command = "make test"\n'
        'static_checks = ["make lint"]\n'
    ))

    config = load_loop_config(studio_root=root)

    assert config.test_command == "make test"
    assert config.static_checks == ["make lint"]


def test_a_leftover_tool_name_is_refused_and_the_message_says_what_to_write(tmp_path):
    """A bare name would run nothing and still report a clean check, so the loop refuses.

    /studio-setup wrote `static_checks = ["ruff"]` into config files and never overwrites
    what it wrote, so these are Studio's own leftovers to clean up.
    """
    root = _python_repo(tmp_path / "py")
    _override(root, '[gate]\nstatic_checks = ["ruff"]\n')

    with pytest.raises(LoopConfigError) as excinfo:
        load_loop_config(studio_root=root)

    message = str(excinfo.value)
    assert str(root / ".studio" / "implementation_loop.toml") in message  # the file to edit
    assert '"ruff"' in message                                           # the entry that is wrong
    assert 'static_checks = ["ruff check {paths}"]' in message           # the line that replaces it


@pytest.mark.parametrize("name, replacement", [
    ("ruff", "ruff check {paths}"),
    ("eslint", "npx eslint {paths}"),
    ("mypy", "mypy {paths}"),
])
def test_every_name_studio_shipped_is_refused_with_its_own_replacement(tmp_path, name, replacement):
    """All three names Studio ever documented, each pointed at the command that replaces it."""
    root = _node_repo(tmp_path / name, {"scripts": {"test": "vitest run"}})
    _override(root, f'[gate]\nstatic_checks = ["{name}"]\n')

    with pytest.raises(LoopConfigError) as excinfo:
        load_loop_config(studio_root=root)

    assert f'static_checks = ["{replacement}"]' in str(excinfo.value)


def test_a_one_word_command_studio_never_shipped_is_taken_as_written(tmp_path):
    """The refusal covers the three values Studio authored, not everything short.

    A "looks like a tool name" heuristic would reject someone's legitimate one-word script,
    and Studio owes a migration only for what it wrote itself.
    """
    root = _python_repo(tmp_path / "py")
    _override(root, '[gate]\nstatic_checks = ["pylint"]\n')

    assert load_loop_config(studio_root=root).static_checks == ["pylint"]


def test_resolve_profile_hands_out_commands_not_tool_names(tmp_path):
    """The detected profile is the merge base for every repo, so it is pinned directly."""
    assert resolve_profile(_python_repo(tmp_path / "py")).static_checks == ("ruff check {paths}",)

    lint_script = _node_repo(tmp_path / "node-script", {"scripts": {"lint": "eslint ."}})
    assert resolve_profile(lint_script).static_checks == ("npm run lint",)

    dependency_only = _node_repo(tmp_path / "node-dep", {"devDependencies": {"eslint": "^9"}})
    assert resolve_profile(dependency_only).static_checks == ("npx eslint {paths}",)

    assert resolve_profile(_node_repo(tmp_path / "node-none", {})).static_checks == ()


def test_refusal_names_unity_and_why_no_command_ships_for_it(tmp_path):
    """Unity is recognised and still refused, for a reason that names the trap."""
    root = _unity_repo(tmp_path)

    with pytest.raises(LoopConfigError) as excinfo:
        load_loop_config(studio_root=root)

    message = str(excinfo.value)
    assert "Detected:   unity (ProjectSettings/ProjectVersion.txt)" in message
    assert "reports success even when it discovered no tests at all" in message


def test_refusal_on_two_stacks_names_both_markers(tmp_path):
    """Cargo.toml beside package.json is refused, not ranked.

    cemetery-security is that repo: a Rust/wasm game whose package.json is CI release
    tooling. Ranking package.json first hands it `npm test`, which passes while testing
    none of the game — a wrong-reason pass, worse than the failure being fixed.
    """
    root = _node_repo(tmp_path, {"scripts": {"test": "npm run ci"}})
    (root / "Cargo.toml").write_text('[package]\nname = "game"\n')

    with pytest.raises(LoopConfigError) as excinfo:
        load_loop_config(studio_root=root)

    message = str(excinfo.value)
    assert "rust (Cargo.toml) and node (package.json) both match" in message
    assert "npm test" not in message


def test_refusal_on_a_recognised_but_unserved_stack(tmp_path):
    """Rust is recognised on its own and still refused: no command is shipped for it."""
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "game"\n')

    with pytest.raises(LoopConfigError) as excinfo:
        load_loop_config(studio_root=tmp_path)

    assert "Detected:   rust (Cargo.toml). Studio ships no test command for Rust." in str(
        excinfo.value
    )


def test_refusal_when_package_json_declares_no_test_script(tmp_path):
    """A Node repo with no `test` script is refused rather than handed `npm test`.

    `npm test` there exits with "missing script: test" — the wrong-reason failure this
    detection exists to remove, so offering it would be the bug wearing a new hat.
    """
    root = _node_repo(tmp_path, {"scripts": {"build": "vite build"}})

    with pytest.raises(LoopConfigError) as excinfo:
        load_loop_config(studio_root=root)

    message = str(excinfo.value)
    assert 'package.json declares no "test" script' in message
    assert "missing script: test" in message


def test_refusal_message_does_not_enumerate_the_known_stacks(tmp_path):
    """The no-match message must not list stacks: it knows more than it serves.

    Naming three while recognising four reads as a contradiction to whoever is holding
    the fourth.
    """
    with pytest.raises(LoopConfigError) as excinfo:
        load_loop_config(studio_root=tmp_path)

    message = str(excinfo.value)
    for stack, _ in STACK_MARKERS:
        assert stack not in message.lower()


def test_refusal_when_the_mutation_check_is_on_with_no_command(tmp_path):
    """Turning the mutation check on without a command to run is refused too.

    Only reachable by hand: no profile ships that pair. It exists so the writer is never
    told to run a check that has nothing to run.
    """
    root = _node_repo(tmp_path, {"scripts": {"test": "vitest run"}})
    _override(root, "[gate]\nrequire_mutation_check = true\n")

    with pytest.raises(LoopConfigError, match="mutation_command"):
        load_loop_config(studio_root=root)


def test_an_override_can_supply_a_command_for_an_unrecognised_repo(tmp_path):
    """Detection failing is not fatal on its own — the override is the way out.

    The refusal is about a gate with no command, not about an unfamiliar repo. This is
    the path the error message tells five repos to take.
    """
    root = tmp_path / "mystery"
    root.mkdir()
    _override(root, '[gate]\ntest_command = "make test"\n')

    config = load_loop_config(studio_root=root)

    assert config.test_command == "make test"
    assert config.static_checks == []


def test_detect_stacks_returns_every_match_in_marker_order(tmp_path):
    """Detection reports all matches; the order is only how the message lists them."""
    (tmp_path / "Cargo.toml").write_text("")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pyproject.toml").write_text("")

    assert detect_stacks(tmp_path) == ["rust", "python", "node"]


def test_detect_stacks_finds_unity_by_a_csproj_glob(tmp_path):
    """The glob half of the marker table works, not just the exact paths."""
    (tmp_path / "Assembly-CSharp.csproj").write_text("<Project />")

    assert detect_stacks(tmp_path) == ["unity"]


def test_detection_ignores_markers_in_subdirectories(tmp_path):
    """Only the repo root is searched, so a vendored tools/package.json can't match."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "package.json").write_text('{"scripts": {"test": "x"}}')

    assert detect_stacks(tmp_path) == []


def test_every_marked_stack_resolves_to_a_profile():
    """Each stack in the marker table has an answer — a command, or a refusal.

    STACK_MARKERS and PROFILES are two lists that could drift apart; adding a marker row
    with no profile behind it would be a KeyError at load in a real repository.
    """
    for stack, _ in STACK_MARKERS:
        assert stack == "node" or stack in PROFILES, f"{stack} has no profile"


def test_a_profiles_static_checks_cannot_be_mutated_through_a_config(tmp_path):
    """PROFILES is shared module state, so its lists must not be handed out by reference.

    A tuple makes that structural instead of something every caller has to remember.
    """
    assert isinstance(PROFILES["python"].static_checks, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        PROFILES["python"].test_command = "npm test"

    config = load_loop_config(studio_root=_python_repo(tmp_path / "py"))
    config.static_checks.append("mypy")

    assert PROFILES["python"].static_checks == ("ruff check {paths}",)
    assert resolve_profile(_python_repo(tmp_path / "py2")).static_checks == ("ruff check {paths}",)


def test_cli_exits_with_the_refusal_and_no_traceback(tmp_path):
    """Run as a script in an unidentifiable repo, the module prints the refusal and stops.

    /forge reads this command's output, so the failure has to arrive as the message
    itself on stderr and a non-zero status — not a traceback, and never a knobs JSON
    carrying an empty test command.
    """
    result = subprocess.run(
        [sys.executable, str(STUDIO_ROOT / "impl_loop.py")],
        capture_output=True,
        text=True,
        env={**os.environ, "STUDIO_ARTIFACT_ROOT": str(tmp_path)},
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("gate.test_command is not set")
    assert "Traceback" not in result.stderr


def test_refusal_on_three_stacks_lists_all_of_them(tmp_path):
    """More than two matches still reads as a sentence, and still names every marker.

    Two is the case a real repo hits today; three is one vendored crate away, and the
    branch that formats it is only ever exercised by a message nobody sees until then.
    """
    root = _node_repo(tmp_path, {"scripts": {"test": "vitest run"}})
    (root / "Cargo.toml").write_text('[package]\nname = "helper"\n')
    (root / "pyproject.toml").write_text('[project]\nname = "tooling"\n')

    with pytest.raises(LoopConfigError) as excinfo:
        load_loop_config(studio_root=root)

    assert (
        "rust (Cargo.toml), python (pyproject.toml) and node (package.json) all match"
        in str(excinfo.value)
    )


def test_an_override_can_replace_the_detected_mutation_command(tmp_path):
    """Every gate key merges over detection, not just the test command."""
    root = _python_repo(tmp_path / "py")
    _override(root, '[gate]\nmutation_command = "cosmic-ray exec"\n')

    config = load_loop_config(studio_root=root)

    assert config.mutation_command == "cosmic-ray exec"
    assert config.test_command == "pytest -q"  # the rest still comes from detection


def test_a_hand_edited_package_json_is_refused_not_crashed(tmp_path):
    """Malformed JSON, or a `scripts` key that isn't a table, reaches the refusal.

    package.json is hand-edited constantly. A traceback out of the config loader would
    be a worse answer than the message that names the file to fix.
    """
    broken_json = tmp_path / "broken"
    broken_json.mkdir()
    (broken_json / "package.json").write_text("{ not json at all")

    scripts_not_a_table = _node_repo(tmp_path / "odd", {"scripts": "vitest run"})

    for root in (broken_json, scripts_not_a_table):
        with pytest.raises(LoopConfigError, match="gate.test_command is not set"):
            load_loop_config(studio_root=root)

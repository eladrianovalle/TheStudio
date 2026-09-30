"""The shipped finish-check Stop hook (specs/shipped-finish-check.md, unit 1).

Almost every promise this hook makes is about the *process*, not the function: exit
status 0 on every path, nothing on stderr, exactly one JSON object on stdout when it
blocks. So the tests here drive `finish_check.py` as a real subprocess with stdin piped,
which is the only way those three are actually observed. The hook reads stdin to EOF, so
it must never be started without input attached or it simply waits.

Two isolations make the subprocess safe to run from a test: `TMPDIR` points the hook's
marker directory into pytest's `tmp_path`, and the override cases run against a *copy* of
the module placed at `.studio/source/finish_check.py` inside `tmp_path`, which is where the
installer puts it. Nothing here writes inside the repository, and an autouse fixture holds
the whole module to that.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import finish_check

STUDIO_DIR = Path(finish_check.__file__).resolve().parent
REPO_ROOT = STUDIO_DIR.parent
MODULE_PATH = STUDIO_DIR / "finish_check.py"

STDLIB_IMPORTS = {"hashlib", "json", "os", "sys", "tempfile", "time"}

MARKER_NAME = re.compile(r"[0-9a-f]{64}\.fired")

# Session ids that would be path traversal, a NUL, or simply too long to be a filename if
# the hook used them unhashed. Each one arrives on stdin, so each one is attacker-supplied.
HOSTILE_SESSION_IDS = [
    "../../x",
    "/etc/passwd",
    "a/b",
    "..",
    "\\..\\x",
    "nul\x00byte",
    "z" * 4096,
]
HOSTILE_IDS = ["dotdot-slash", "absolute", "subdir", "dotdot", "backslash", "nul", "4kb"]

SENTINEL_BYTES = b"planted by test_finish_check; the hook must never touch this\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_hook(payload, *, tmpdir, script=None, cwd=None) -> subprocess.CompletedProcess:
    """Run the hook as its own process, with *payload* on stdin and markers under *tmpdir*."""
    if isinstance(payload, dict):
        payload = json.dumps(payload)
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    env = dict(os.environ)
    for name in ("TMPDIR", "TEMP", "TMP"):
        env[name] = str(tmpdir)
    return subprocess.run(
        [sys.executable, str(script or MODULE_PATH)],
        input=payload,
        capture_output=True,
        env=env,
        cwd=str(cwd or tmpdir),
    )


# Restated independently of the module, like the digest below it: the directory is
# per-user so that a shared /tmp cannot be used to plant one session's marker.
MARKER_DIR_NAME = "studio-finish-check-%d" % os.getuid()


def _expected_marker(tmpdir, session_id: str) -> Path:
    """Where the marker for *session_id* belongs, restated independently of the module."""
    digest = hashlib.sha256(session_id.encode("utf-8", "replace")).hexdigest()
    return Path(tmpdir) / MARKER_DIR_NAME / ("%s.fired" % digest)


def _raw_marker_path(marker_dir, session_id: str) -> str:
    """Where the marker would land if the session id were used unhashed — the bug we guard."""
    return os.path.join(str(marker_dir), "%s.fired" % session_id)


def _plant_sentinel(marker_dir, session_id: str, inside: Path):
    """Put a file where an unhashed session id would have pointed, if that path is ours to write.

    Some of the hostile ids point clean out of *inside*, the test's own directory — `/etc/passwd`
    resolves to `/etc/passwd.fired`, which a run as root would really create — and some cannot be a
    path at all (a NUL byte, a 4 KB name). For those the test falls back to asserting the hook
    created nothing there.
    """
    raw = _raw_marker_path(marker_dir, session_id)
    boundary = str(inside)
    try:
        if os.path.commonpath([os.path.abspath(raw), boundary]) != boundary:
            return None
        os.makedirs(os.path.dirname(raw), exist_ok=True)
        with open(raw, "wb") as handle:
            handle.write(SENTINEL_BYTES)
    except (OSError, ValueError):
        return None
    return Path(raw)


def _files_under(root) -> set:
    return {path for path in Path(root).rglob("*") if path.is_file()}


def _git_status() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.skip("git is not available, so repository cleanliness cannot be checked")
    return result.stdout


def _repo_files() -> list[Path]:
    """Every file git knows about, including ones added but not yet committed."""
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.skip("git is not available, so the repository cannot be enumerated")
    return [REPO_ROOT / name for name in result.stdout.split("\0") if name]


def _imported_roots(path: Path) -> set:
    """Top-level module names imported by a file, however the import is spelled."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hook_tmp(tmp_path):
    """The temp directory the hook is pointed at.

    Nested two levels deep on purpose: a `../..` traversal out of the marker directory
    then lands somewhere inside `tmp_path`, where the test can see what happened to it.
    """
    temp_root = tmp_path / "outer" / "inner" / "tempdir"
    temp_root.mkdir(parents=True)
    return temp_root


@pytest.fixture
def installed_module(tmp_path):
    """A copy of the hook where the installer puts it: `.studio/source/finish_check.py`."""
    source_dir = tmp_path / "install" / ".studio" / "source"
    source_dir.mkdir(parents=True)
    copy = source_dir / "finish_check.py"
    shutil.copy2(MODULE_PATH, copy)
    return copy


@pytest.fixture(autouse=True)
def repository_stays_clean():
    """No test in this file may write a file inside the repository.

    The override paragraph is resolved from the module's own location, so a test that ran
    the repo's own copy would look for `<repo>/finish-check.txt` — and a careless test
    would create it. Every test here is held to leaving the working tree byte-identical.
    """
    before = _git_status()
    yield
    assert _git_status() == before, "a test changed the repository working tree"
    assert not (REPO_ROOT / "finish-check.txt").exists()


# ---------------------------------------------------------------------------
# Criterion 1 — stdlib only, and no Studio module
# ---------------------------------------------------------------------------

def test_the_hook_imports_only_the_six_standard_library_modules():
    assert _imported_roots(MODULE_PATH) == STDLIB_IMPORTS


def test_the_hook_imports_no_studio_module():
    """Asserted here directly, because test_stdlib_only.py deliberately permits these.

    A Studio module can raise while being imported, which happens before any of the
    hook's own error handling exists — so a single Studio import would reintroduce the
    one failure this file cannot swallow.
    """
    studio_modules = {path.stem for path in STUDIO_DIR.glob("*.py")}
    studio_packages = {
        entry.name for entry in STUDIO_DIR.iterdir() if (entry / "__init__.py").exists()
    }
    assert _imported_roots(MODULE_PATH) & (studio_modules | studio_packages) == set()


# ---------------------------------------------------------------------------
# Criterion 2 — block once, then allow
# ---------------------------------------------------------------------------

def test_the_first_stop_is_blocked_and_the_second_is_allowed(hook_tmp):
    payload = {"session_id": "ordinary-session", "stop_hook_active": False}
    marker = _expected_marker(hook_tmp, "ordinary-session")

    blocked = _run_hook(payload, tmpdir=hook_tmp)
    assert blocked.returncode == 0
    assert blocked.stderr == b""
    lines = blocked.stdout.decode("utf-8").strip().splitlines()
    assert len(lines) == 1
    decision = json.loads(lines[0])
    assert decision == {"decision": "block", "reason": finish_check.DEFAULT_REASON}
    assert marker.exists()

    allowed = _run_hook(payload, tmpdir=hook_tmp)
    assert allowed.returncode == 0
    assert allowed.stdout == b""
    assert allowed.stderr == b""
    assert not marker.exists()


def test_stop_hook_active_allows_the_stop_and_clears_the_marker(hook_tmp):
    """The primary loop guard: the harness sets this on the retry our block caused."""
    marker = _expected_marker(hook_tmp, "retry-session")
    blocked = _run_hook({"session_id": "retry-session"}, tmpdir=hook_tmp)
    assert json.loads(blocked.stdout.decode("utf-8"))["decision"] == "block"
    assert marker.exists()

    allowed = _run_hook(
        {"session_id": "retry-session", "stop_hook_active": True}, tmpdir=hook_tmp
    )
    assert allowed.returncode == 0
    assert allowed.stdout == b""
    assert not marker.exists()


def test_a_second_session_is_blocked_even_while_another_marker_is_fresh(hook_tmp):
    """Markers are per session, so one session's block cannot silence another's check."""
    first = _run_hook({"session_id": "session-one"}, tmpdir=hook_tmp)
    second = _run_hook({"session_id": "session-two"}, tmpdir=hook_tmp)
    assert json.loads(first.stdout.decode("utf-8"))["decision"] == "block"
    assert json.loads(second.stdout.decode("utf-8"))["decision"] == "block"
    assert _expected_marker(hook_tmp, "session-one").exists()
    assert _expected_marker(hook_tmp, "session-two").exists()


# ---------------------------------------------------------------------------
# Criterion 3 — nothing on stdin can make it fail
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw",
    ["", "not json", "[]", '"x"', "3"],
    ids=["empty", "not-json", "json-list", "json-string", "json-number"],
)
def test_unusable_stdin_still_blocks_cleanly(raw, hook_tmp):
    """None of these five is a payload, and the check still has to happen on every one of them.

    The last three parse as valid JSON and would make `payload.get` raise without the `isinstance`
    check — so each would reach the user as a traceback on stderr instead of blocking the stop.
    """
    result = _run_hook(raw, tmpdir=hook_tmp)
    assert result.returncode == 0
    assert result.stderr == b""
    assert json.loads(result.stdout.decode("utf-8"))["decision"] == "block"


def test_eight_kilobytes_of_binary_noise_exits_zero(hook_tmp):
    noise = bytes(range(256)) * 32
    assert len(noise) == 8192
    result = _run_hook(noise, tmpdir=hook_tmp)
    assert result.returncode == 0
    assert result.stderr == b""


def test_an_exception_raised_inside_main_still_exits_zero(hook_tmp, tmp_path):
    """The top-level guard, exercised by making a real call inside `main` blow up."""
    script = tmp_path / "forced_failure.py"
    script.write_text(
        "import sys\n"
        "sys.path.insert(0, %r)\n" % str(STUDIO_DIR)
        + "import finish_check\n"
        "def explode(session_id):\n"
        "    raise RuntimeError('forced failure inside main')\n"
        "finish_check.marker_path = explode\n"
        "finish_check.run()\n",
        encoding="utf-8",
    )
    result = _run_hook({"session_id": "boom"}, tmpdir=hook_tmp, script=script)
    assert result.returncode == 0
    assert result.stdout == b""
    assert result.stderr == b""


# ---------------------------------------------------------------------------
# Criterion 4 — a hostile session id cannot escape the marker directory
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("session_id", HOSTILE_SESSION_IDS, ids=HOSTILE_IDS)
def test_every_marker_is_a_direct_child_of_one_directory(session_id):
    path = finish_check.marker_path(session_id)
    parent, name = os.path.split(path)
    assert parent == finish_check.MARKER_DIR
    assert MARKER_NAME.fullmatch(name)


def test_a_symlink_left_at_the_marker_path_is_not_written_through(hook_tmp, tmp_path):
    """On a shared /tmp, somebody else's symlink must not become our write target.

    The symlink has to dangle to reach the write at all. One pointing at a file
    that exists is either spent as a fresh marker or swept as a stale one, and
    both of those delete the link rather than follow it. A dangling one survives
    both — `getmtime` raises for it — and lands on the open, where following it
    would create a file of our choosing at a path of the attacker's.

    The per-user marker directory is the first defence; this is the second.
    Refusing to write also costs us the marker, so the hook lets the stop
    through: a marker it cannot record is one it cannot trust.
    """
    marker_dir = hook_tmp / MARKER_DIR_NAME
    marker_dir.mkdir()
    target = tmp_path / "file-the-attacker-wants-created"
    _expected_marker(hook_tmp, "symlinked-session").symlink_to(target)

    result = _run_hook({"session_id": "symlinked-session"}, tmpdir=hook_tmp)

    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == b""
    assert not target.exists()


@pytest.mark.parametrize("session_id", HOSTILE_SESSION_IDS, ids=HOSTILE_IDS)
def test_a_hostile_session_id_touches_only_its_own_hashed_marker(
    session_id, hook_tmp, tmp_path
):
    marker_dir = hook_tmp / MARKER_DIR_NAME
    marker_dir.mkdir()
    sentinel = _plant_sentinel(marker_dir, session_id, inside=tmp_path)
    before = _files_under(tmp_path)

    blocked = _run_hook({"session_id": session_id}, tmpdir=hook_tmp)
    assert blocked.returncode == 0
    assert json.loads(blocked.stdout.decode("utf-8"))["decision"] == "block"
    assert _files_under(tmp_path) - before == {_expected_marker(hook_tmp, session_id)}

    allowed = _run_hook({"session_id": session_id}, tmpdir=hook_tmp)
    assert allowed.returncode == 0
    assert allowed.stdout == b""
    assert _files_under(tmp_path) == before

    if sentinel is not None:
        assert sentinel.read_bytes() == SENTINEL_BYTES
    else:
        # Nothing could be planted there, so the check is that nothing arrived either.
        # A NUL-bearing id has no expressible path at all — the tree comparison above is
        # the whole assertion for that one.
        raw = _raw_marker_path(marker_dir, session_id)
        if "\0" not in raw:
            assert not os.path.lexists(raw)


# ---------------------------------------------------------------------------
# Criterion 5 — markers live in the temp directory, never in a repository
# ---------------------------------------------------------------------------

def test_every_marker_resolves_under_the_system_temp_directory():
    """Containment, not a copy of the constant: a real marker path lands inside the temp directory."""
    system_temp = tempfile.gettempdir()
    path = finish_check.marker_path("any-session")
    assert os.path.commonpath([system_temp, path]) == system_temp


def test_running_the_hook_leaves_the_repository_untouched(hook_tmp):
    """The autouse fixture checks the tree; this is the run that gives it something to catch."""
    _run_hook({"session_id": "repo-cleanliness"}, tmpdir=hook_tmp, cwd=REPO_ROOT)
    _run_hook({"session_id": "repo-cleanliness"}, tmpdir=hook_tmp, cwd=REPO_ROOT)
    assert _files_under(hook_tmp / MARKER_DIR_NAME) == set()


# ---------------------------------------------------------------------------
# Criterion 6 — the override paragraph
# ---------------------------------------------------------------------------

def _reason_printed_by(script, hook_tmp, session_id, cwd) -> str:
    result = _run_hook({"session_id": session_id}, tmpdir=hook_tmp, script=script, cwd=cwd)
    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    return json.loads(result.stdout.decode("utf-8"))["reason"]


@pytest.fixture
def unrelated_cwd(tmp_path):
    """A working directory with nothing to do with the module — the override must ignore it."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    return elsewhere


def test_a_readable_override_replaces_the_default_paragraph(
    installed_module, hook_tmp, unrelated_cwd
):
    override = installed_module.parents[1] / "finish-check.txt"
    override.write_text("Check the migration notes before you stop.\n", encoding="utf-8")

    reason = _reason_printed_by(installed_module, hook_tmp, "override-present", unrelated_cwd)
    assert reason == "Check the migration notes before you stop.\n"


def test_an_absent_override_falls_back_to_the_default(
    installed_module, hook_tmp, unrelated_cwd
):
    assert not (installed_module.parents[1] / "finish-check.txt").exists()
    reason = _reason_printed_by(installed_module, hook_tmp, "override-absent", unrelated_cwd)
    assert reason == finish_check.DEFAULT_REASON


@pytest.mark.parametrize("content", ["", "   \n\t\n"], ids=["empty", "whitespace"])
def test_an_empty_override_falls_back_to_the_default(
    content, installed_module, hook_tmp, unrelated_cwd
):
    (installed_module.parents[1] / "finish-check.txt").write_text(content, encoding="utf-8")
    reason = _reason_printed_by(installed_module, hook_tmp, "override-empty", unrelated_cwd)
    assert reason == finish_check.DEFAULT_REASON


def test_an_unreadable_override_falls_back_to_the_default(
    installed_module, hook_tmp, unrelated_cwd
):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root can read a mode-000 file, so there is nothing to test")
    override = installed_module.parents[1] / "finish-check.txt"
    override.write_text("unreadable paragraph\n", encoding="utf-8")
    override.chmod(0o000)
    try:
        reason = _reason_printed_by(
            installed_module, hook_tmp, "override-unreadable", unrelated_cwd
        )
    finally:
        override.chmod(0o600)
    assert reason == finish_check.DEFAULT_REASON


def test_an_oversized_override_falls_back_to_the_default(
    installed_module, hook_tmp, unrelated_cwd
):
    override = installed_module.parents[1] / "finish-check.txt"
    override.write_text("x" * (finish_check.OVERRIDE_MAX_BYTES + 1), encoding="utf-8")
    reason = _reason_printed_by(installed_module, hook_tmp, "override-oversized", unrelated_cwd)
    assert reason == finish_check.DEFAULT_REASON


def test_the_override_is_resolved_from_the_module_not_the_working_directory(
    installed_module, hook_tmp, unrelated_cwd
):
    """A decoy beside the working directory must lose to the real location, and to nothing."""
    (unrelated_cwd / "finish-check.txt").write_text("decoy paragraph\n", encoding="utf-8")
    reason = _reason_printed_by(installed_module, hook_tmp, "override-decoy", unrelated_cwd)
    assert reason == finish_check.DEFAULT_REASON


# ---------------------------------------------------------------------------
# Criterion 7 — one copy of the mechanism in the repository
# ---------------------------------------------------------------------------

def test_the_old_hook_file_is_gone():
    assert not (REPO_ROOT / ".claude" / "hooks" / "finish-check.py").exists()


def test_the_hooks_readme_no_longer_says_the_installer_ships_nothing_from_it():
    readme = (REPO_ROOT / ".claude" / "hooks" / "README.md").read_text(encoding="utf-8")
    for stale_claim in (
        "the installer does not ship them",
        "nothing in this directory reaches a consuming repo",
        "does not ship",
        "ships nothing",
    ):
        assert stale_claim not in readme
    assert "studio/finish_check.py" in readme


def test_the_default_paragraph_lives_in_exactly_one_file():
    carriers = set()
    for path in _repo_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if finish_check.DEFAULT_REASON in text:
            carriers.add(path.relative_to(REPO_ROOT).as_posix())
    assert carriers == {"studio/finish_check.py"}

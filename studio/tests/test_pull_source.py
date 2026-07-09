"""Tests for the opt-in source fast-forward primitives (Units 1+2 of the spec).

These verify the two pure additions in ``install.py``:

- ``_source_auto_pull_enabled`` — reads ``[update] auto_pull_source`` from the
  SOURCE repo's own ``.studio/update.toml``.
- ``_fast_forward_source`` — safely fast-forwards a cleanly-behind source checkout
  to its origin, mutating nothing unless every precondition holds.

All fixtures are hermetic. Each test builds a real temp git repo under
``tmp_path`` wired to a LOCAL BARE remote (``git init --bare``), then advances the
remote through a throwaway clone so the ``source`` checkout's local default branch
is strictly BEHIND origin without having fetched. Nothing here touches the network.
"""
import argparse
import shutil
import subprocess

import install
from install import _fast_forward_source, _source_auto_pull_enabled


def _git(repo, *args):
    """Run a git command in ``repo``, failing loudly on error, output swallowed."""
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    )


def _head(repo):
    """Return the current HEAD commit SHA of ``repo``."""
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _make_source(tmp_path, name="src"):
    """Create a source repo on ``main`` wired to a bare origin, main pushed.

    Returns ``(repo_path, remote_path)``. The clone has a ``studio/`` dir and one
    commit, and ``origin/main`` tracks the pushed branch.
    """
    remote = tmp_path / f"{name}.git"
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "--bare", "-q", str(remote)],
        check=True,
    )
    repo = tmp_path / name
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q", str(repo)],
        check=True,
    )
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "remote", "add", "origin", str(remote))
    (repo / "studio").mkdir()
    (repo / "studio" / "run_phase.py").write_text("# studio\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    _git(repo, "push", "-q", "-u", "origin", "main")
    return repo, remote


def _advance_origin(tmp_path, remote):
    """Push one new commit onto the bare ``remote``'s main branch.

    Done through a throwaway clone so the source repo's cached ``origin/main``
    stays put until it chooses to fetch. Returns the new origin HEAD SHA.
    """
    clone = tmp_path / "advancer"
    subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
    _git(clone, "config", "user.email", "t@t")
    _git(clone, "config", "user.name", "t")
    (clone / "advance.txt").write_text("advance\n", encoding="utf-8")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "advance")
    _git(clone, "push", "-q", "origin", "main")
    return _head(clone)


def _behind_source(tmp_path, name="src"):
    """Build a source repo whose local main is strictly behind origin/main.

    Returns ``(repo, remote, staleness)`` where ``staleness`` is a real
    ``SourceStaleness`` obtained via ``_source_staleness(fetch=True)`` — so
    ``origin/main`` is fetched and ``is_stale`` is True, exactly as production
    hands it to ``_fast_forward_source``.
    """
    repo, remote = _make_source(tmp_path, name=name)
    _advance_origin(tmp_path, remote)
    staleness = install._source_staleness(repo, fetch=True)
    assert staleness.is_stale
    return repo, remote, staleness


# --- _source_auto_pull_enabled -------------------------------------------------


def _write_update_toml(repo, body):
    studio = repo / ".studio"
    studio.mkdir(exist_ok=True)
    (studio / "update.toml").write_text(body, encoding="utf-8")


def test_auto_pull_enabled_true_when_opted_in(tmp_path):
    repo, _ = _make_source(tmp_path)
    _write_update_toml(repo, "[update]\nauto_pull_source = true\n")
    assert _source_auto_pull_enabled(repo) is True


def test_auto_pull_false_when_flag_off(tmp_path):
    repo, _ = _make_source(tmp_path)
    _write_update_toml(repo, "[update]\nauto_pull_source = false\n")
    assert _source_auto_pull_enabled(repo) is False


def test_auto_pull_false_when_file_missing(tmp_path):
    repo, _ = _make_source(tmp_path)
    assert _source_auto_pull_enabled(repo) is False


def test_auto_pull_false_when_update_table_missing(tmp_path):
    repo, _ = _make_source(tmp_path)
    _write_update_toml(repo, "[other]\nauto_pull_source = true\n")
    assert _source_auto_pull_enabled(repo) is False


def test_auto_pull_false_when_key_missing(tmp_path):
    repo, _ = _make_source(tmp_path)
    _write_update_toml(repo, "[update]\nsomething_else = true\n")
    assert _source_auto_pull_enabled(repo) is False


def test_auto_pull_false_on_malformed_toml(tmp_path):
    repo, _ = _make_source(tmp_path)
    _write_update_toml(repo, "[update]\nauto_pull_source = = broken\n")
    assert _source_auto_pull_enabled(repo) is False


def test_auto_pull_false_on_non_git_dir(tmp_path):
    plain = tmp_path / "not_a_repo"
    plain.mkdir()
    # Even with the config present, a non-git dir has no toplevel → False.
    _write_update_toml(plain, "[update]\nauto_pull_source = true\n")
    assert _source_auto_pull_enabled(plain) is False


# --- _fast_forward_source ------------------------------------------------------


def test_ff_pulls_clean_behind_source(tmp_path):
    repo, remote, staleness = _behind_source(tmp_path)
    origin_head = _head(tmp_path / "advancer")

    result = _fast_forward_source(repo, staleness)

    assert result.pulled is True
    assert result.reason is None
    assert result.new_head is not None
    # Source HEAD now equals origin's HEAD.
    assert _head(repo) == origin_head
    # It was a fast-forward, not a merge: HEAD has a single parent (no merges).
    merge_count = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", "--merges", "main"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert merge_count == "0"


def test_ff_skips_dirty_tree(tmp_path):
    repo, _, staleness = _behind_source(tmp_path)
    before = _head(repo)
    # Modify a tracked file so the working tree is dirty.
    (repo / "studio" / "run_phase.py").write_text("# dirty\n", encoding="utf-8")

    result = _fast_forward_source(repo, staleness)

    assert result.pulled is False
    assert result.new_head is None
    assert "uncommitted" in result.reason
    assert _head(repo) == before  # HEAD unchanged


def test_ff_skips_on_feature_branch(tmp_path):
    repo, _, staleness = _behind_source(tmp_path)
    before = _head(repo)
    _git(repo, "checkout", "-q", "-b", "feat")

    result = _fast_forward_source(repo, staleness)

    assert result.pulled is False
    assert result.new_head is None
    assert "feat" in result.reason
    assert _head(repo) == before  # HEAD unchanged


def test_ff_skips_when_diverged(tmp_path):
    repo, _, staleness = _behind_source(tmp_path)
    # Add a local commit on the source's default branch: now both ahead AND behind.
    (repo / "local_work.txt").write_text("local\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "local work")
    before = _head(repo)

    result = _fast_forward_source(repo, staleness)

    assert result.pulled is False
    assert result.new_head is None
    assert "diverged" in result.reason or "fast-forward" in result.reason
    assert _head(repo) == before  # HEAD unchanged


# --- update_studio wiring + CLI output (Units 3+4) -----------------------------
#
# These drive the whole opt-in end to end. A FULL, installable copy of the real
# studio/ tree is committed to a bare-remote-backed source repo, a consumer is
# installed from it, then origin is advanced one commit so the source's local main
# trails it. Auto-resolve is routed at the hermetic source by monkeypatching
# ``install._get_studio_root`` (the same trick the source-staleness tests use), so
# ``update_studio(consumer)`` resolves the source cleanly and ``enabled`` is True.

STUDIO_ROOT = install._get_studio_root()


def _installable_source_behind(tmp_path, monkeypatch):
    """Build a full installable Studio source whose local main is BEHIND origin,
    install a consumer from it, and route auto-resolve at the source.

    Returns ``(source, consumer, marker)`` where ``source`` is the ``studio/`` dir
    inside the source repo, ``consumer`` is the installed target, and ``marker`` is
    the text the advance commit appended to ``run_phase.py`` on origin — so a
    re-install that reads the caught-up tree snapshots it into the consumer.
    """
    root = tmp_path / "src"
    source = root / "studio"
    shutil.copytree(
        STUDIO_ROOT, source,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".pytest_cache", "output", "knowledge",
        ),
    )
    remote = tmp_path / "origin.git"
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "--bare", "-q", str(remote)],
        check=True,
    )
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q", str(root)],
        check=True,
    )
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "remote", "add", "origin", str(remote))
    # Gitignore .studio/ so the per-machine update.toml the opt-in lives in never
    # dirties the tree — mirrors the real repo, and is what keeps the ff unblocked.
    (root / ".gitignore").write_text(
        ".studio/\nstudio/output/\nstudio/knowledge/\n__pycache__/\n", encoding="utf-8"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    _git(root, "push", "-q", "-u", "origin", "main")

    # Consumer installed from the source AT the old commit.
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    install.install_studio(consumer, source)

    # Advance origin one commit that touches a real source file, so a re-install
    # from the caught-up tree visibly drifts the consumer's snapshot. Done through
    # a throwaway clone; the source's local main stays put until it fetches.
    marker = "# pull-source integration marker\n"
    clone = tmp_path / "advancer"
    subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
    _git(clone, "config", "user.email", "t@t")
    _git(clone, "config", "user.name", "t")
    run_phase_py = clone / "studio" / "run_phase.py"
    run_phase_py.write_text(
        run_phase_py.read_text(encoding="utf-8") + marker, encoding="utf-8"
    )
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "advance")
    _git(clone, "push", "-q", "origin", "main")

    monkeypatch.setattr(install, "_get_studio_root", lambda: source)
    return source, consumer, marker


def _update_args(target, **overrides):
    """Build the argparse namespace ``_do_update`` reads."""
    base = dict(target=target, force=False, no_fetch=False, no_hook=True, pull_source=False)
    base.update(overrides)
    return argparse.Namespace(**base)


def test_update_auto_pull_fast_forwards_source(tmp_path, monkeypatch):
    """Source config opts in + source is cleanly behind → update_studio (auto-
    resolved) fast-forwards the source, clears staleness, and re-installs from the
    caught-up LOCAL tree (no origin worktree materialized)."""
    source, consumer, marker = _installable_source_behind(tmp_path, monkeypatch)
    _write_update_toml(source.parent, "[update]\nauto_pull_source = true\n")
    origin_head = _head(tmp_path / "advancer")

    result = install.update_studio(consumer)

    assert result["source_pull"]["pulled"] is True
    assert result["staleness"] is None
    assert result["source_note"] is None          # clean fast path → LOCAL tree read
    assert _head(source) == origin_head           # source caught up to origin
    # The re-install read the caught-up local tree: its marker is now snapshotted.
    snapshot = (consumer / ".studio" / "source" / "run_phase.py").read_text(encoding="utf-8")
    assert marker in snapshot


def test_update_opted_in_but_dirty_falls_back(tmp_path, monkeypatch):
    """Opted in but the source working tree is dirty → the ff is skipped with a
    reason and the update falls back to today's origin/main path (staleness intact)."""
    source, consumer, _ = _installable_source_behind(tmp_path, monkeypatch)
    _write_update_toml(source.parent, "[update]\nauto_pull_source = true\n")
    # Dirty a TRACKED source file so the ff precondition (clean tree) fails.
    tracked = source / "run_phase.py"
    tracked.write_text(tracked.read_text(encoding="utf-8") + "# local edit\n", encoding="utf-8")

    result = install.update_studio(consumer)

    assert result["source_pull"]["pulled"] is False
    assert result["source_pull"]["reason"]
    assert result["staleness"]["is_stale"] is True   # fell back to origin path


def test_update_not_opted_in_unchanged(tmp_path, monkeypatch):
    """No config and no flag → no pull is attempted and the staleness path is
    byte-for-byte today's behavior (read from origin, print the nag)."""
    source, consumer, _ = _installable_source_behind(tmp_path, monkeypatch)

    result = install.update_studio(consumer)

    assert result["source_pull"] is None
    assert result["staleness"]["is_stale"] is True
    assert result["source_note"]                     # read from origin, as before


def test_update_pull_source_flag_overrides_absent_config(tmp_path, monkeypatch):
    """The --pull-source flag forces the ff even with no config present."""
    source, consumer, _ = _installable_source_behind(tmp_path, monkeypatch)
    origin_head = _head(tmp_path / "advancer")

    result = install.update_studio(consumer, pull_source=True)

    assert result["source_pull"]["pulled"] is True
    assert result["staleness"] is None
    assert _head(source) == origin_head


def test_do_update_prints_fast_forwarded(tmp_path, monkeypatch, capsys):
    """_do_update prints the 'Fast-forwarded ...' line on a successful pull."""
    import run_phase

    source, consumer, _ = _installable_source_behind(tmp_path, monkeypatch)
    _write_update_toml(source.parent, "[update]\nauto_pull_source = true\n")

    run_phase._do_update(_update_args(consumer))

    out = capsys.readouterr().out
    assert "Fast-forwarded your Studio source to" in out
    assert "Catch your source up:" not in out


def test_do_update_prints_nag_when_not_opted_in(tmp_path, monkeypatch, capsys):
    """Not opted in over a stale source → the existing manual-pull nag prints."""
    import run_phase

    source, consumer, _ = _installable_source_behind(tmp_path, monkeypatch)

    run_phase._do_update(_update_args(consumer))

    out = capsys.readouterr().out
    assert "Catch your source up:" in out
    assert "Fast-forwarded" not in out


def test_do_update_prints_couldnt_when_ff_blocked(tmp_path, monkeypatch, capsys):
    """Opted in but the ff couldn't run → the 'Wanted to ... but couldn't' line prints."""
    import run_phase

    source, consumer, _ = _installable_source_behind(tmp_path, monkeypatch)
    _write_update_toml(source.parent, "[update]\nauto_pull_source = true\n")
    tracked = source / "run_phase.py"
    tracked.write_text(tracked.read_text(encoding="utf-8") + "# local edit\n", encoding="utf-8")

    run_phase._do_update(_update_args(consumer))

    out = capsys.readouterr().out
    assert "Wanted to fast-forward your Studio source but couldn't:" in out

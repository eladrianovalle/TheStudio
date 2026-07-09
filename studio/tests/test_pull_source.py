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


def _advance_origin(tmp_path, remote, commits=1, clone_name="advancer"):
    """Push ``commits`` new commits onto the bare ``remote``'s main branch.

    Done through a throwaway clone so the source repo's cached ``origin/main``
    stays put until it chooses to fetch. Returns the new origin HEAD SHA.
    """
    clone = tmp_path / clone_name
    subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
    _git(clone, "config", "user.email", "t@t")
    _git(clone, "config", "user.name", "t")
    for index in range(commits):
        marker = f"{clone_name}_c{index}"
        (clone / f"{marker}.txt").write_text(f"{marker}\n", encoding="utf-8")
        _git(clone, "add", "-A")
        _git(clone, "commit", "-qm", marker)
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

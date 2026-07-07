"""Tests for source-staleness detection (`_source_staleness` and friends).

These verify the detection helper that lets check-install/update refuse a false
"up to date" when the Studio source checkout is itself behind its git remote.

All fixtures are hermetic: each test builds a real temp git repo under
``tmp_path`` wired to a LOCAL BARE remote (`git init --bare`), so nothing here
touches the network. The one network-shaped case (a fetch that times out) is
simulated by monkeypatching ``_git_fetch`` to return False, which is exactly what
a timeout produces — no flaky real URLs.
"""
import subprocess

import install
from install import _source_staleness


def _git(repo, *args):
    """Run a git command in ``repo``, failing loudly on error, output swallowed."""
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    )


def _make_repo_with_remote(tmp_path, name="src"):
    """Create a local git repo ``name`` on ``main`` wired to a bare origin remote.

    Both the repo and its bare remote (``<name>.git``) share one initial commit on
    ``main``, and ``main`` tracks ``origin/main``. Returns (repo_path, remote_path).
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
    (repo / "f.txt").write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    _git(repo, "push", "-q", "-u", "origin", "main")
    return repo, remote


def _commit(repo, filename, text):
    """Add a file and commit it in ``repo``."""
    (repo / filename).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", f"add {filename}")


def _advance_origin(tmp_path, remote, commits, clone_name="advancer"):
    """Push ``commits`` new commits onto the bare ``remote``'s main branch.

    Done through a throwaway clone so the original repo's cached ``origin/main``
    stays put until it chooses to fetch — that gap is what several tests exercise.
    """
    clone = tmp_path / clone_name
    subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
    _git(clone, "config", "user.email", "t@t")
    _git(clone, "config", "user.name", "t")
    for index in range(commits):
        _commit(clone, f"c{index}.txt", f"c{index}\n")
    _git(clone, "push", "-q", "origin", "main")


def test_local_behind_origin_is_stale(tmp_path):
    repo, remote = _make_repo_with_remote(tmp_path)
    _advance_origin(tmp_path, remote, 2)
    # Refresh the cached origin/main so refs-only detection can see it's behind.
    _git(repo, "fetch", "-q", "origin", "main")

    result = _source_staleness(repo, fetch=False)

    assert result.is_stale is True
    assert result.behind == 2
    assert result.remote_ref == "origin/main"


def test_even_is_not_stale(tmp_path):
    repo, _ = _make_repo_with_remote(tmp_path)

    result = _source_staleness(repo, fetch=False)

    assert result.is_stale is False
    assert result.behind == 0
    assert result.remote_ref == "origin/main"


def test_ahead_only_is_not_stale(tmp_path):
    repo, _ = _make_repo_with_remote(tmp_path)
    # A local commit that was never pushed: ahead of origin, behind by nothing.
    _commit(repo, "local.txt", "local only\n")

    result = _source_staleness(repo, fetch=False)

    assert result.is_stale is False
    assert result.behind == 0


def test_never_fetched_origin_caught_only_when_fetching(tmp_path):
    """A remote configured but never fetched has no origin/main tracking ref yet.
    fetch=True establishes it and catches the staleness; fetch=False can't see it.
    Guards the fetch-before-ref-check ordering."""
    repo, remote = _make_repo_with_remote(tmp_path)
    _advance_origin(tmp_path, remote, 2)
    # Simulate "remote added by hand, never fetched": drop the tracking ref.
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")

    # No fetch → no tracking ref to compare against → bows out, not stale.
    refs_only = _source_staleness(repo, fetch=False)
    assert refs_only.is_stale is False
    assert refs_only.remote_ref is None

    # A fetch creates the ref first, then the staleness is caught.
    fetched = _source_staleness(repo, fetch=True)
    assert fetched.is_stale is True
    assert fetched.behind == 2
    assert fetched.fetched is True
    assert fetched.remote_ref == "origin/main"


def test_diverged_is_stale(tmp_path):
    repo, remote = _make_repo_with_remote(tmp_path)
    # Local gains its own commit; origin gains a different one → the branches fork.
    _commit(repo, "local.txt", "local only\n")
    _advance_origin(tmp_path, remote, 1)
    _git(repo, "fetch", "-q", "origin", "main")

    result = _source_staleness(repo, fetch=False)

    assert result.is_stale is True
    assert result.behind == 1


def test_no_remote_configured_is_not_stale(tmp_path):
    repo = tmp_path / "plain"
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q", str(repo)],
        check=True,
    )
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _commit(repo, "f.txt", "v1\n")

    result = _source_staleness(repo, fetch=False)

    assert result.is_stale is False
    assert result.remote_ref is None
    assert result.reason is not None


def test_not_a_git_repo_is_not_stale(tmp_path):
    plain = tmp_path / "not_git"
    plain.mkdir()

    result = _source_staleness(plain, fetch=False)

    assert result.is_stale is False
    assert result.remote_ref is None
    assert result.reason is not None


def test_detached_head_without_default_branch_is_not_stale(tmp_path):
    repo, _ = _make_repo_with_remote(tmp_path)
    # Detach HEAD, then drop the local default branch entirely: there is no
    # main/master to compare, so detection must bow out rather than guess.
    _git(repo, "checkout", "-q", "--detach", "HEAD")
    _git(repo, "branch", "-D", "main")

    result = _source_staleness(repo, fetch=False)

    assert result.is_stale is False
    assert result.reason is not None


def test_fetch_false_uses_cached_refs(tmp_path):
    repo, remote = _make_repo_with_remote(tmp_path)
    # Origin moves ahead, but the repo never fetches: with fetch=False the stale
    # cached origin/main is all detection sees, so it reports "even".
    _advance_origin(tmp_path, remote, 1)

    result = _source_staleness(repo, fetch=False)

    assert result.is_stale is False
    assert result.behind == 0


def test_fetch_true_catches_unfetched_origin(tmp_path):
    repo, remote = _make_repo_with_remote(tmp_path)
    # Origin has commits the repo has NOT fetched — the real bug this feature
    # fixes. A default fetch must pull them into view and report stale.
    _advance_origin(tmp_path, remote, 2)

    result = _source_staleness(repo, fetch=True)

    assert result.is_stale is True
    assert result.behind == 2
    assert result.fetched is True


def test_fetch_timeout_falls_back_to_cached_refs(tmp_path, monkeypatch):
    repo, remote = _make_repo_with_remote(tmp_path)
    _advance_origin(tmp_path, remote, 2)
    # Simulate a timed-out / failed fetch deterministically (no real network).
    monkeypatch.setattr(install, "_git_fetch", lambda *args, **kwargs: False)

    result = _source_staleness(repo, fetch=True)

    assert result.fetched is False
    assert result.is_stale is False
    assert result.behind == 0
    assert result.reason is not None

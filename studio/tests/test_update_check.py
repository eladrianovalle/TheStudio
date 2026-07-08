"""Tests for the proactive update-availability nudge (Unit 1 of the spec).

These verify ``compute_update_check`` and the ``check-updates`` handler
(``_do_check_updates``): a consuming repo learns whether its installed Studio
snapshot is behind the upstream source it was installed from.

All fixtures are hermetic. Each test builds a real temp git repo under
``tmp_path`` wired to a LOCAL BARE remote (``git init --bare``), so nothing here
touches the network. The installed ``target`` is faked with a hand-written
``.studio/VERSION`` whose ``commit`` is a real SHA from the source repo, and
whose ``source_path`` points at that source. ``compute_update_check`` resolves
the source through ``_resolve_source_dir`` exactly as production does; we route
that resolution through the recorded ``source_path`` by monkeypatching
``_get_studio_root`` to the target's snapshot dir (the production shape: the hook
runs from ``.studio/source``, so the studio root IS the snapshot).

``now`` is injected for TTL determinism. ``_git_fetch`` is monkeypatched only
where a test asserts fetch-called-or-not.
"""
import json
import subprocess
import types

import install
from install import compute_update_check
from run_phase import _do_check_updates


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


def _make_source(tmp_path, name="src", push=True):
    """Create a Studio source repo on ``main`` (with a ``run_phase.py`` marker).

    Wired to a bare origin remote. When ``push`` it pushes ``main`` and sets up
    the ``origin/main`` tracking ref; when not, the remote is configured but
    never fetched (no ``refs/remotes/origin/main`` — the offline-first-run case).
    Returns ``(repo_path, remote_path)``.
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
    # _resolve_source_dir only accepts a source dir that has a run_phase.py.
    (repo / "run_phase.py").write_text("# studio\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    if push:
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
        name = f"{clone_name}_c{index}"
        (clone / f"{name}.txt").write_text(f"{name}\n", encoding="utf-8")
        _git(clone, "add", "-A")
        _git(clone, "commit", "-qm", name)
    _git(clone, "push", "-q", "origin", "main")
    return _head(clone)


def _make_target(tmp_path, source_dir, installed_commit, monkeypatch, name="proj"):
    """Build a fake installed target: ``.studio/VERSION`` + snapshot resolution.

    Writes ``VERSION`` with ``commit`` and ``source_path``, then monkeypatches
    ``_get_studio_root`` to the target's ``.studio/source`` so ``_resolve_source_dir``
    routes through the recorded ``source_path`` (production's snapshot shape).
    Returns the target path.
    """
    target = tmp_path / name
    studio = target / ".studio"
    studio.mkdir(parents=True)
    (studio / "VERSION").write_text(
        json.dumps({"commit": installed_commit, "source_path": str(source_dir)}),
        encoding="utf-8",
    )
    snapshot = (studio / "source").resolve()
    monkeypatch.setattr(install, "_get_studio_root", lambda: snapshot)
    return target


def _write_cache(target, cache):
    (target / ".studio" / "update-check.json").write_text(
        json.dumps(cache), encoding="utf-8"
    )


def _read_cache(target):
    return json.loads(
        (target / ".studio" / "update-check.json").read_text(encoding="utf-8")
    )


def _cache_exists(target):
    return (target / ".studio" / "update-check.json").exists()


# --- 1. update-available: notify True + handler prints the JSON banner ---

def test_update_available_notifies_and_handler_prints(tmp_path, monkeypatch, capsys):
    source, remote = _make_source(tmp_path)
    installed = _head(source)          # snapshot installed from the original commit
    _advance_origin(tmp_path, remote)  # upstream moved past it
    target = _make_target(tmp_path, source, installed, monkeypatch)

    result = compute_update_check(target, now=1000.0)
    assert result.should_notify is True

    # Clear the latch the direct call just wrote, then drive the real handler.
    (target / ".studio" / "update-check.json").unlink()
    _do_check_updates(types.SimpleNamespace(target=str(target)))

    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert payload["hookSpecificOutput"]["additionalContext"] == (
        install.UPDATE_ADDITIONAL_CONTEXT
    )


# --- 2. up-to-date: notify False, handler prints nothing ---

def test_up_to_date_is_silent(tmp_path, monkeypatch, capsys):
    source, _ = _make_source(tmp_path)
    installed = _head(source)  # VERSION.commit == origin/main HEAD
    target = _make_target(tmp_path, source, installed, monkeypatch)

    result = compute_update_check(target, now=1000.0)
    assert result.should_notify is False

    _do_check_updates(types.SimpleNamespace(target=str(target)))
    assert capsys.readouterr().out == ""


# --- 3. offline fallback: no origin ref, fetch fails -> silent, no raise, no cache ---

def test_offline_fallback_is_silent(tmp_path, monkeypatch):
    source, _ = _make_source(tmp_path, push=False)  # no origin/main tracking ref
    installed = _head(source)
    target = _make_target(tmp_path, source, installed, monkeypatch)
    monkeypatch.setattr(install, "_git_fetch", lambda *a, **k: False)

    result = compute_update_check(target, now=1000.0)

    assert result.should_notify is False
    # No source_commit resolved -> no cache, so the next online session retries.
    assert not _cache_exists(target)


# --- 4. TTL cache hit: verdict from cache, fetch never called ---

def test_ttl_cache_hit_skips_fetch(tmp_path, monkeypatch):
    source, remote = _make_source(tmp_path)
    installed = _head(source)
    upstream = _advance_origin(tmp_path, remote)  # a real newer SHA
    target = _make_target(tmp_path, source, installed, monkeypatch)

    def _boom(*a, **k):
        raise AssertionError("fetch must not be called on a fresh cache")

    monkeypatch.setattr(install, "_git_fetch", _boom)
    # Fresh cache (last_check == now) holding the upstream SHA the source never fetched.
    _write_cache(target, {"last_check": 1000.0, "source_commit": upstream,
                          "notified_commit": None})

    result = compute_update_check(target, now=1000.0)

    assert result.should_notify is True  # cached upstream != installed, unnotified


# --- 5. notify-once: first call latches, second call (same HEAD) stays silent ---

def test_notify_once(tmp_path, monkeypatch):
    source, remote = _make_source(tmp_path)
    installed = _head(source)
    _advance_origin(tmp_path, remote)
    target = _make_target(tmp_path, source, installed, monkeypatch)

    first = compute_update_check(target, now=1000.0)  # real fetch, notifies + latches
    assert first.should_notify is True

    # Second call within the TTL: cache is fresh, no fetch, same HEAD already latched.
    second = compute_update_check(target, now=1000.0)
    assert second.should_notify is False


# --- 6. re-arm: upstream advances again -> notifies again once TTL expires ---

def test_rearm_on_new_commit(tmp_path, monkeypatch):
    source, remote = _make_source(tmp_path)
    installed = _head(source)
    _advance_origin(tmp_path, remote, clone_name="adv1")
    target = _make_target(tmp_path, source, installed, monkeypatch)

    first = compute_update_check(target, now=1000.0)
    assert first.should_notify is True

    _advance_origin(tmp_path, remote, clone_name="adv2")  # upstream moves again
    # Past the TTL so the check fetches and sees the newer HEAD.
    later = 1000.0 + install.UPDATE_CHECK_TTL_SECONDS + 1
    third = compute_update_check(target, now=later)
    assert third.should_notify is True


# --- 7. updated inside TTL clears: installed catches up -> banner clears, no fetch ---

def test_updated_inside_ttl_clears(tmp_path, monkeypatch):
    source, remote = _make_source(tmp_path)
    installed = _head(source)
    upstream = _advance_origin(tmp_path, remote)
    target = _make_target(tmp_path, source, installed, monkeypatch)

    def _boom(*a, **k):
        raise AssertionError("fetch must not be called on a fresh cache")

    monkeypatch.setattr(install, "_git_fetch", _boom)
    # Fresh cache says upstream is at X and we already notified for X.
    _write_cache(target, {"last_check": 1000.0, "source_commit": upstream,
                          "notified_commit": upstream})
    # User ran /studio-update: the installed commit is now X (== upstream).
    (target / ".studio" / "VERSION").write_text(
        json.dumps({"commit": upstream, "source_path": str(source)}),
        encoding="utf-8",
    )

    result = compute_update_check(target, now=1000.0)

    assert result.should_notify is False  # recomputed live: update_available False


# --- 8. garbage target: handler neither raises nor exits non-zero ---

def test_handler_exit_zero_on_garbage_target(tmp_path, capsys):
    garbage = tmp_path / "does-not-exist"

    # Direct call must not raise and must print nothing.
    _do_check_updates(types.SimpleNamespace(target=str(garbage)))
    assert capsys.readouterr().out == ""

    # And the real CLI process exits 0.
    import sys
    from pathlib import Path
    studio_dir = Path(install.__file__).resolve().parent
    proc = subprocess.run(
        [sys.executable, str(studio_dir / "run_phase.py"),
         "check-updates", "--target", str(garbage)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""

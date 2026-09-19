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
import sys
import types
from pathlib import Path

import install
import run_phase
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


def test_load_update_cache_discards_bad_last_check(tmp_path):
    """A hand-edited/corrupt cache whose last_check isn't a number is treated as a
    cold start, not left to blow up the TTL math (`now - last_check`) later. Guards
    the compute_update_check "never raises" contract."""
    from install import _load_update_cache, UPDATE_CHECK_CACHE

    studio = tmp_path / ".studio"
    studio.mkdir(parents=True)
    (studio / UPDATE_CHECK_CACHE).write_text(
        json.dumps({"last_check": "not-a-number", "source_commit": "abc123"}),
        encoding="utf-8",
    )
    assert _load_update_cache(tmp_path) == {}


def test_load_update_cache_discards_non_string_commit(tmp_path):
    """A cache whose commit fields are the wrong type is discarded, so the SHA
    compares can't raise on a corrupt file."""
    from install import _load_update_cache, UPDATE_CHECK_CACHE

    studio = tmp_path / ".studio"
    studio.mkdir(parents=True)
    (studio / UPDATE_CHECK_CACHE).write_text(
        json.dumps({"last_check": 123.0, "source_commit": ["not", "a", "str"]}),
        encoding="utf-8",
    )
    assert _load_update_cache(tmp_path) == {}


# === The session brief: unfinished planned work (Unit 3 of the completion ledger) ===
#
# `check-updates` has two sources of news now, and they are deliberately independent: an
# available Studio update, and a unit an approved spec planned that nothing ever built. These
# tests hold the seam between them — that either can speak alone, that both fit in one object,
# and above all that a failure in one can never silence the other.

_STUDIO_DIR = Path(install.__file__).resolve().parent


def _init_repo(path):
    """A real git work tree at ``path`` with one commit, so `git log` has something to answer."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q", str(path)], check=True
    )
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    _git(path, "commit", "-q", "--allow-empty", "-m", "init")
    return path


def _spec_text(build_plan, *, status="approved", slug="a-feature"):
    """A spec file's text: frontmatter, a little prose, then the plan under test."""
    return (
        "---\n"
        "feature: A Feature\n"
        f"slug: {slug}\n"
        f"status: {status}\n"
        "---\n\n"
        "# A Feature\n\nSome prose.\n\n"
        f"{build_plan}"
    )


# Two units owed and one already built, which is the shape the brief has to get right: it
# names the first owed unit, counts both, and says nothing about the built one.
_TWO_OWED = (
    "## Build Plan\n\n"
    "### 1. `already_built` — the one that is done\n\n"
    "### 2. `still_owed` — the one nobody built\n\n"
    "### 3. `also_owed` — the one after that\n"
)


def _seed_spec(target, build_plan, *, status="approved", name="a-feature.md"):
    specs = target / "specs"
    specs.mkdir(exist_ok=True)
    (specs / name).write_text(
        _spec_text(build_plan, status=status, slug=name[:-3]), encoding="utf-8"
    )
    return specs / name


def _brief(tmp_path, build_plan=_TWO_OWED, *built, name="brief"):
    """A target repo holding an approved spec, with ``built`` recorded as writer commits."""
    target = _init_repo(tmp_path / name)
    _seed_spec(target, build_plan)
    for unit_id in built:
        _git(target, "commit", "-q", "--allow-empty", "-m", f"writer: {unit_id}")
    return target


def _context(capsys):
    """The single JSON object the handler printed, or None when it printed nothing."""
    out = capsys.readouterr().out
    if not out.strip():
        return None
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


# --- 9. the brief names one unit and the command that continues it ---

def test_brief_names_the_next_unit_its_spec_and_the_forge_command(tmp_path, capsys):
    """Criterion 1: everything a fresh session needs to act, in one sentence.

    There is no Studio update here (the target has no VERSION), so the unfinished block is
    speaking entirely on its own — which is the day-one case, since every install is current.
    """
    target = _brief(tmp_path, _TWO_OWED, "already_built")

    _do_check_updates(types.SimpleNamespace(target=str(target)))
    context = _context(capsys)

    assert "Unfinished planned work: 2 units in 1 approved spec." in context
    assert "`still_owed`" in context
    assert "specs/a-feature.md" in context
    assert "the one nobody built" in context
    assert "/forge --spec specs/a-feature.md --unit still_owed" in context
    assert "open a PR adding `- **Dropped:** YYYY-MM-DD — <reason>`" in context
    assert "all branches including unmerged ones" in context
    # One named action, not a list: the second owed unit is counted, never listed, and the
    # built one is not mentioned at all.
    assert "also_owed" not in context
    assert "already_built" not in context


def test_two_specs_sharing_a_slug_each_keep_their_own_path(tmp_path, capsys):
    """Rule 7 forbids a duplicate `unit_id`, not a duplicate slug.

    Keyed on slug alone, the second spec read would overwrite the first, and the brief would
    send a session to a file that never planned the unit it just named.
    """
    target = _init_repo(tmp_path / "shared-slug")
    specs = target / "specs"
    specs.mkdir()
    for name, unit_id in (("a-feature.md", "first_owed"), ("b-feature.md", "second_owed")):
        (specs / name).write_text(
            _spec_text(f"## Build Plan\n\n### 1. `{unit_id}` — what {unit_id} is for\n",
                       slug="shared"),
            encoding="utf-8",
        )

    _do_check_updates(types.SimpleNamespace(target=str(target)))
    context = _context(capsys)

    assert "`first_owed`" in context
    assert "specs/a-feature.md" in context
    assert "specs/b-feature.md" not in context
    # And the count reads the files too: counted by slug these two would read as one spec.
    assert "in 2 approved specs" in context


# --- 10. update-only output is byte-identical to what shipped a month ago ---

def test_update_only_output_is_unchanged(tmp_path, monkeypatch, capsys):
    """Criterion 2: the installs that see only the update line must see exactly today's bytes."""
    source, remote = _make_source(tmp_path)
    installed = _head(source)
    _advance_origin(tmp_path, remote)
    target = _make_target(tmp_path, source, installed, monkeypatch)  # no specs dir at all

    _do_check_updates(types.SimpleNamespace(target=str(target)))

    assert capsys.readouterr().out == json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": install.UPDATE_ADDITIONAL_CONTEXT,
        }
    }) + "\n"


# --- 11. both sources: one object, update first, blank line between ---

def test_both_sources_share_one_object_update_first(tmp_path, monkeypatch, capsys):
    source, remote = _make_source(tmp_path)
    installed = _head(source)
    _advance_origin(tmp_path, remote)
    target = _make_target(tmp_path, source, installed, monkeypatch)
    _init_repo(target)
    _seed_spec(target, _TWO_OWED)
    _git(target, "commit", "-q", "--allow-empty", "-m", "writer: already_built")

    _do_check_updates(types.SimpleNamespace(target=str(target)))
    out = capsys.readouterr().out

    assert out.count("hookSpecificOutput") == 1  # one object, not two
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    update, unfinished = context.split("\n\n")
    assert update == install.UPDATE_ADDITIONAL_CONTEXT
    assert unfinished.startswith("Unfinished planned work:")
    assert "/forge --spec specs/a-feature.md --unit still_owed" in unfinished


# --- 12. neither source has news: nothing at all, and the process still exits 0 ---

def test_no_news_prints_nothing_and_exits_zero(tmp_path, capsys):
    """Not an empty JSON object: a nudge that fires with no news is one people learn to skip."""
    target = _brief(tmp_path, _TWO_OWED, "already_built", "still_owed", "also_owed")

    _do_check_updates(types.SimpleNamespace(target=str(target)))
    assert capsys.readouterr().out == ""

    proc = subprocess.run(
        [sys.executable, str(_STUDIO_DIR / "run_phase.py"),
         "check-updates", "--target", str(target)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""


# --- 13. the two guards are crossed: neither failure can silence the other source ---

def test_a_broken_ledger_still_prints_the_update(tmp_path, monkeypatch, capsys):
    """The nudge ten installs depend on cannot be taken down by one malformed spec."""
    source, remote = _make_source(tmp_path)
    installed = _head(source)
    _advance_origin(tmp_path, remote)
    target = _make_target(tmp_path, source, installed, monkeypatch)

    def _explode(_target):
        raise RuntimeError("a spec this repo cannot parse")

    monkeypatch.setattr(run_phase, "_unfinished_context", _explode)
    _do_check_updates(types.SimpleNamespace(target=str(target)))

    assert _context(capsys) == install.UPDATE_ADDITIONAL_CONTEXT


def test_a_broken_update_check_still_prints_the_unfinished_work(tmp_path, monkeypatch, capsys):
    target = _brief(tmp_path, _TWO_OWED, "already_built")

    def _explode(*args, **kwargs):
        raise RuntimeError("the update check fell over")

    monkeypatch.setattr(install, "compute_update_check", _explode)
    _do_check_updates(types.SimpleNamespace(target=str(target)))

    context = _context(capsys)
    assert context.startswith("Unfinished planned work:")
    assert install.UPDATE_ADDITIONAL_CONTEXT not in context


# --- 14. the escape hatch: a dropped unit stops being counted ---

def test_dropping_a_unit_moves_the_brief_on_and_then_silences_it(tmp_path, capsys):
    """Criterion 4: the only two honest ways to stop the nudge are build it or drop it."""
    target = _brief(tmp_path, _TWO_OWED, "already_built")
    spec_path = target / "specs" / "a-feature.md"

    spec_path.write_text(
        _spec_text(
            "## Build Plan\n\n"
            "### 1. `already_built` — the one that is done\n\n"
            "### 2. `still_owed` — the one nobody built\n"
            "- **Dropped:** 2026-09-18 — superseded by `also_owed`.\n\n"
            "### 3. `also_owed` — the one after that\n"
        ),
        encoding="utf-8",
    )
    _do_check_updates(types.SimpleNamespace(target=str(target)))
    context = _context(capsys)
    assert "Unfinished planned work: 1 unit in 1 approved spec." in context
    assert "/forge --spec specs/a-feature.md --unit also_owed" in context
    assert "still_owed" not in context

    spec_path.write_text(
        _spec_text(
            "## Build Plan\n\n"
            "### 1. `already_built` — the one that is done\n\n"
            "### 2. `still_owed` — the one nobody built\n"
            "- **Dropped:** 2026-09-18 — superseded.\n\n"
            "### 3. `also_owed` — the one after that\n"
            "- **Dropped:** 2026-09-18 — not wanted after all.\n"
        ),
        encoding="utf-8",
    )
    _do_check_updates(types.SimpleNamespace(target=str(target)))
    assert capsys.readouterr().out == ""


# --- 15. the specs directory comes from --target, never from the working directory ---

def test_specs_are_read_from_the_target_not_the_working_directory(tmp_path):
    """Criterion 5: the hook runs from wherever the session opened, which proves nothing.

    Run as a real process from a subdirectory of an unrelated git repo — the case that breaks
    any cwd-derived lookup — and the brief must still be about the target.
    """
    target = _brief(tmp_path, _TWO_OWED, "already_built")
    elsewhere = _init_repo(tmp_path / "unrelated")
    _seed_spec(elsewhere, "## Build Plan\n\n### 1. `someone_elses_unit` — not ours\n")
    subdir = elsewhere / "deep" / "down"
    subdir.mkdir(parents=True)

    proc = subprocess.run(
        [sys.executable, str(_STUDIO_DIR / "run_phase.py"),
         "check-updates", "--target", str(target)],
        capture_output=True, text=True, cwd=str(subdir),
    )

    assert proc.returncode == 0
    context = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "/forge --spec specs/a-feature.md --unit still_owed" in context
    assert "someone_elses_unit" not in context


# --- 16. every way of not knowing ends in silence, never a nag ---

def test_a_target_with_no_git_says_nothing(tmp_path, capsys):
    """With no built set every planned unit reads unbuilt, so the brief would nag about all
    of them. "I cannot see" and "nothing was built" are different answers."""
    target = tmp_path / "no-git"
    target.mkdir()
    _seed_spec(target, _TWO_OWED)

    _do_check_updates(types.SimpleNamespace(target=str(target)))
    assert capsys.readouterr().out == ""


def test_an_unreadable_spec_is_skipped_rather_than_fatal(tmp_path, capsys):
    """A directory named like a spec makes `read_text` raise; the brief reads on regardless."""
    target = _brief(tmp_path, _TWO_OWED, "already_built", "still_owed", "also_owed")
    (target / "specs" / "broken.md").mkdir()
    _seed_spec(target, "## Build Plan\n\n### 1. `readable_unit` — still readable\n",
               name="b-feature.md")

    _do_check_updates(types.SimpleNamespace(target=str(target)))
    context = _context(capsys)

    assert "/forge --spec specs/b-feature.md --unit readable_unit" in context


def test_an_installed_repo_reads_its_studio_specs_directory(tmp_path, capsys):
    """A consuming repo keeps its specs under `.studio/specs`; the source repo uses `specs/`.

    Both layouts exist on this machine, and the installed one wins where it is present — a
    repo that has run `studio init` has a `.studio/` and may have a `specs/` of its own that
    means something else entirely.
    """
    target = _init_repo(tmp_path / "installed")
    installed_specs = target / ".studio" / "specs"
    installed_specs.mkdir(parents=True)
    (installed_specs / "a-feature.md").write_text(
        _spec_text("## Build Plan\n\n### 1. `the_installed_unit` — owed here\n"),
        encoding="utf-8",
    )
    _seed_spec(target, "## Build Plan\n\n### 1. `not_a_studio_spec` — somebody else's\n")

    _do_check_updates(types.SimpleNamespace(target=str(target)))
    context = _context(capsys)

    assert "/forge --spec .studio/specs/a-feature.md --unit the_installed_unit" in context
    assert ".studio/specs/a-feature.md" in context
    assert "not_a_studio_spec" not in context

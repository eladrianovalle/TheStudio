# Reviewer concern — finish_check_ships_with_studio

## Concern

The guard behind criterion 5 is narrower than the criterion it is credited with. The autouse
fixture in `studio/tests/test_finish_check.py` checks the repository with:

```python
    before = _git_status()
    yield
    assert _git_status() == before, "a test changed the repository working tree"
    assert not (REPO_ROOT / "finish-check.txt").exists()
```

`git status --porcelain` says nothing about a file written into a path the repo already
ignores — `studio/output/`, `.scratch/`, `.private/`. So "no test run writes any file inside
the repository" is asserted for tracked and untracked-but-visible paths only. The one write
this unit could realistically make by accident, `<repo>/finish-check.txt`, is caught by the
second assertion, so nothing is wrong today; the gap is that the fixture would not catch a
future test that wrote somewhere ignored.

## Why it was not fixed in this pass

`load_bearing` — the writer flagged this fixture as the thing that holds criterion 5 across
every test in the file, so rewriting its check was out of bounds for the editor.

## Smallest follow-up that would resolve it

Snapshot the repository as a file set rather than as git's opinion of it: take
`{p for p in REPO_ROOT.rglob("*") if p.is_file()}` before and after, minus `.git/`, and compare.
One line each side, and it no longer depends on what is ignored. If that turns out to be too
slow across 1332 tests, narrow it to the handful of directories a stray write could land in.

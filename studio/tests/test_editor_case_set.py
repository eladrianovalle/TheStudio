"""Check the tracked editor benchmark recipes without building any historical trees."""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest

DATASET = Path(__file__).resolve().parents[1] / "evals" / "forge_editor"
CASE_FILES = sorted((DATASET / "cases").glob("*.json"))
TELLTALE_WORDS = (
    "eval", "case", "plant", "defect", "clean", "test", "fixture", "judge", "measure", "probe",
)
SHA = re.compile(r"[0-9a-f]{40}")
HUNK_HEADER = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def _read_case(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_telltale_word(text):
    return any(word in text.lower() for word in TELLTALE_WORDS)


def _added_lines(patch):
    old_remaining = new_remaining = 0
    for line in patch.splitlines():
        if header := HUNK_HEADER.match(line):
            old_remaining, new_remaining = (int(count or 1) for count in header.groups())
        elif old_remaining or new_remaining:
            if line.startswith("+"):
                new_remaining -= 1
                yield line[1:]
            elif line.startswith("-"):
                old_remaining -= 1
            elif line.startswith(" "):
                old_remaining -= 1
                new_remaining -= 1


@pytest.mark.parametrize("path", CASE_FILES, ids=lambda path: path.stem)
def test_case_shape(path):
    case = _read_case(path)
    assert case["kind"] in {"clean", "defect"}
    assert case["source"] in {"as_built", "plant", "review_fix"}
    assert not _contains_telltale_word(path.stem)
    assert SHA.fullmatch(case["writer_sha"])
    assert all(case[field].strip() for field in ("unit_id", "spec_file", "test_command"))

    criteria = case["acceptance_criteria"]
    assert isinstance(criteria, list) and criteria
    assert all(isinstance(criterion, str) and criterion.strip() for criterion in criteria)

    if case["kind"] == "defect":
        assert case["defect"].strip()
        assert case["probe"]
        number = case["breaks_criterion"]
        assert number is None or (type(number) is int and 1 <= number <= len(criteria))

    if probe := case.get("probe"):
        assert SHA.fullmatch(probe["from_sha"])
        assert isinstance(probe["paths"], list)
        assert probe["command"].strip()

    if case["source"] == "plant":
        assert case["kind"] == "defect" and case["breaks_criterion"] is not None
        patch = DATASET / "patches" / case["patch"]
        assert patch.resolve().parent == DATASET / "patches"
        assert patch.is_file(), patch
        for line in _added_lines(patch.read_text(encoding="utf-8")):
            assert not _contains_telltale_word(line), (patch.name, line)


def test_case_set_has_enough_unique_trees():
    names = [path.stem.casefold() for path in CASE_FILES]
    assert len(names) == len(set(names))
    kinds = Counter(_read_case(path)["kind"] for path in CASE_FILES)
    assert kinds["defect"] >= 12, kinds
    assert kinds["clean"] >= 6, kinds


def test_review_fixes_have_matching_twins():
    by_fix = defaultdict(list)
    for path in CASE_FILES:
        case = _read_case(path)
        if case["source"] == "review_fix":
            fix = case["fix_sha"]
            assert SHA.fullmatch(fix), path
            by_fix[fix].append(case)

    for fix, cases in by_fix.items():
        assert sorted(case["kind"] for case in cases) == ["clean", "defect"], fix
        first, second = cases
        for field in ("unit_id", "writer_sha", "acceptance_criteria", "test_command", "probe"):
            assert first[field] == second[field], (fix, field)

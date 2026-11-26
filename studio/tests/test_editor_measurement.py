"""Regression gate for the newest recorded measurement of the current editor and cases."""
import re
import shutil
from collections import Counter

import pytest

import editor_results as measurement
from test_enforced_rules import JUDGED

MEASURE_AGAIN = (
    "Run `python studio/editor_measure.py build` in a fresh worktree and paste the line it prints."
)
NO_RECORDED_LAUNCH = (
    "The mark was set from runs with no recorded launch. Record two baseline runs and set the mark again."
)


def check_mark(results, linked):
    assert results["judge"] == measurement.JUDGE
    mark = results["mark"]
    assert (mark is not None) == linked, "Set the mark and the editor rule's results link together"
    if mark is None:
        return
    by_id = {run["run_id"]: run for run in results["runs"]}
    ids = mark["baseline_runs"]
    assert len(ids) == len(set(ids)) == 2 and all(i in by_id for i in ids), "Missing or repeated baseline"
    for key in ("prompt_fingerprint", "cases_fingerprint"):
        assert by_id[ids[0]][key] == by_id[ids[1]][key], f"Baseline runs differ in {key}"


def check_run(results, current, names, model):
    if not results["runs"]:
        assert results["mark"] is None
        return
    run = next((r for r in reversed(results["runs"]) if all(r[k] == v for k, v in current.items())), None)
    if run is None:
        moved = [key for key, value in current.items() if value != results["runs"][-1][key]]
        raise AssertionError(f"{', '.join(moved)} changed. {MEASURE_AGAIN}")
    assert model in run["model"], f"Unexpected editor model {run['model']}"
    assert Counter(r["case"] for r in run["cases"]) == Counter(names), "Missing, extra or repeated case"
    for row in run["cases"]:
        assert row["outcome"] in {"caught", "missed", "repaired", "passed", "false_alarm"}, row
        if row.get("ruled"):
            assert row.get("note", "").strip(), row
    if mark := results["mark"]:
        baselines = [r for r in results["runs"] if r["run_id"] in mark["baseline_runs"]]
        if run.get("launch_fingerprint"):
            assert all(b.get("launch_fingerprint") for b in baselines), NO_RECORDED_LAUNCH
        counts = measurement.totals(run)
        assert counts["missed"] <= mark["max_missed"] and counts["false_alarm"] <= mark["max_false_alarms"], (
            f"Measured {counts['missed']} missed, {counts['false_alarm']} false alarms against {mark}"
        )


def test_tracked_mark_matches_rule():
    row, = [r for r in JUDGED if r.rule == measurement.RULE]
    path = measurement.DATASET / "results.json"
    if row.results is not None:
        assert measurement.STUDIO.parent / row.results == path and path.is_file()
    check_mark(measurement.read_results(path), row.results is not None)


def test_tracked_cases_have_a_measurement():
    results = measurement.read_results(measurement.DATASET / "results.json")
    if results["runs"]:
        fingerprint = measurement.cases_fingerprint(measurement.DATASET / "cases", measurement.DATASET / "patches")
        assert any(r["cases_fingerprint"] == fingerprint for r in results["runs"]), (
            f"cases_fingerprint changed. {MEASURE_AGAIN}"
        )


def test_tracked_run_matches_editor_and_cases():
    results = measurement.read_results(measurement.DATASET / "results.json")
    if not results["runs"]:
        return
    cases = measurement.DATASET / "cases"
    patches = measurement.DATASET / "patches"
    if not shutil.which("node"):
        pytest.skip("computing the current editor fingerprint requires node")
    current = measurement.fingerprints(cases, patches, measurement.settings())
    model = measurement.node("render", [])["model"]
    check_run(results, current, [p.stem for p in cases.glob("*.json")], model)


def sample():
    return {"judge": measurement.JUDGE, "mark": None, "runs": [
        {"run_id": "a", "model": "claude-opus", "cases": [{"case": "oak", "outcome": "missed"}],
         "prompt_fingerprint": "p", "cases_fingerprint": "c"}]}


CURRENT = {"prompt_fingerprint": "p", "cases_fingerprint": "c"}


@pytest.mark.parametrize("key", list(CURRENT))
def test_changed_and_restored_fingerprint(key):
    results = sample()
    with pytest.raises(AssertionError, match=re.escape(f"{key} changed. {MEASURE_AGAIN}")):
        check_run(results, {**CURRENT, key: "different"}, ["oak"], "opus")
    results["runs"].append({**results["runs"][0], key: "different", "cases": []})
    check_run(results, CURRENT, ["oak"], "opus")


@pytest.mark.parametrize("changes", [
    {"cases": []}, {"cases": [{"case": "elm", "outcome": "passed"}]},
    {"cases": [{"case": "oak", "outcome": "needs_ruling"}]},
    {"cases": [{"case": "oak", "outcome": "caught", "ruled": True, "note": " "}]},
    {"model": "sonnet"},
])
def test_refuses_invalid_newest_matching_run(changes):
    results = sample()
    results["runs"].append({**results["runs"][0], **changes})
    with pytest.raises(AssertionError):
        check_run(results, CURRENT, ["oak"], "opus")


def test_marks_require_two_matching_baselines_and_a_link():
    results = sample()
    with pytest.raises(AssertionError):
        check_mark(results, True)
    results["mark"] = {"baseline_runs": ["a", "b"], "max_missed": 0, "max_false_alarms": 0}
    with pytest.raises(AssertionError):
        check_mark(results, False)
    with pytest.raises(AssertionError):
        check_mark(results, True)
    results["runs"].append({**results["runs"][0], "run_id": "b", "cases_fingerprint": "d"})
    with pytest.raises(AssertionError):
        check_mark(results, True)
    results["runs"][-1]["cases_fingerprint"] = "c"
    check_mark(results, True)
    for outcome in ("missed", "false_alarm"):
        results["runs"][-1]["cases"][0]["outcome"] = outcome
        with pytest.raises(AssertionError, match="against"):
            check_run(results, CURRENT, ["oak"], "opus")


def test_a_run_with_a_recorded_launch_is_not_judged_against_a_mark_set_without_one():
    results = sample()
    results["runs"].append({**results["runs"][0], "run_id": "b"})
    results["mark"] = {"baseline_runs": ["a", "b"], "max_missed": 1, "max_false_alarms": 0}
    check_mark(results, True)
    check_run(results, CURRENT, ["oak"], "opus")

    results["runs"].append({**results["runs"][0], "run_id": "c", "launch_fingerprint": "launch-1"})
    with pytest.raises(AssertionError, match=re.escape(NO_RECORDED_LAUNCH)):
        check_run(results, CURRENT, ["oak"], "opus")

    results["runs"][1]["launch_fingerprint"] = "launch-1"
    with pytest.raises(AssertionError, match=re.escape(NO_RECORDED_LAUNCH)):
        check_run(results, CURRENT, ["oak"], "opus")

    results["runs"][0]["launch_fingerprint"] = "launch-0"
    check_run(results, CURRENT, ["oak"], "opus")


def test_baselines_and_spread_compare_only_the_prompt_and_cases_fingerprints(capsys):
    row = {"case": "oak", "kind": "clean", "outcome": "passed", "gate": {"passed": True}}
    results = sample()
    results["runs"] = [
        {**results["runs"][0], "run_id": "a", "cases": [row]},
        {**results["runs"][0], "run_id": "b", "cases": [{**row, "outcome": "false_alarm"}],
         "launch_fingerprint": "launch-1", "claude_code_version": "2.1.332"},
    ]
    results["mark"] = {"baseline_runs": ["a", "b"], "max_missed": 0, "max_false_alarms": 1}
    check_mark(results, True)

    measurement.report(results, results["runs"][1])
    assert "Spread from a: 1 oak" in capsys.readouterr().out

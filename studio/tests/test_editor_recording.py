"""Replay small workflow journals through the public record and rule commands."""
import json
import shutil
import subprocess

import pytest

import editor_measure
import editor_results as measurement


def jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


@pytest.fixture
def recording(tmp_path, monkeypatch):
    output = tmp_path / "studio/output/editor_measure/current"
    output.mkdir(parents=True)
    cases = tmp_path / "cases"
    cases.mkdir()
    config = tmp_path / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    workflow = config / "projects/project/session/subagents/workflows/wf-one"
    workflow.mkdir(parents=True)
    tree = tmp_path / "checkout"
    tree.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    subprocess.run(["git", "-c", "user.name=Editor", "-c", "user.email=editor@example.org",
                    "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "writer"], cwd=tree, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tree, text=True).strip()
    manifest = {"built_at": "2026-01-01T00:00:00Z", "model": "opus", "cases": [],
                "prompt_fingerprint": "p", "cases_fingerprint": "c"}
    journal = []
    for i, name in enumerate(("caught", "repaired", "needs_ruling", "missed", "passed", "false_alarm")):
        directory = tmp_path / name
        shutil.copytree(tree, directory)
        valid = i >= 4
        case = {"name": name, "tree": str(directory), "head": head, "prompt": f"Review {name}",
                "acceptance_criteria": ["Score visible"], "kind": "clean" if valid else "defect",
                "breaks_criterion": 1, "source": "review_fix", "defect": "Score disappears.",
                "probe": {"paths": [], "command": "git diff --quiet --exit-code HEAD -- repair.txt",
                          "from_sha": head}}
        if not valid:
            # A real command sees an editor repair (including an uncommitted file).
            case["probe"]["command"] = "python -c \"from pathlib import Path; assert Path('repair.txt').exists()\""
        if name == "repaired":
            (directory / "repair.txt").touch()
        manifest["cases"].append(case)
        verdict = "fail" if name == "caught" else "pass"
        grade = {"criterion": "Score visible", "verdict": verdict, "evidence": "Inspect the score"}
        editor = {"criteria_verdicts": [grade], "tests": {"passed": True}, "mvi_verdict": name != "false_alarm",
                  "unresolved_concerns": ["Possibly hidden"] if name == "needs_ruling" else []}
        journal.extend([{"type": "started", "agentId": str(i), "label": name},
                        {"type": "result", "agentId": str(i), "result": editor, "toolsUsed": ["Read"]}])
        jsonl(workflow / f"agent-{i}.jsonl", [
            {"type": "user", "timestamp": "2026-01-02T00:00:00Z", "message": {"content": case["prompt"]}},
            {"type": "assistant", "message": {"model": "claude-opus-4"}},
        ])
    measurement.write(output / "manifest.json", manifest)
    jsonl(workflow / "journal.jsonl", journal)

    def cli(*args):
        return editor_measure.main(list(args), cases, tmp_path / "patches", tmp_path)

    return cli, tmp_path / "results.json", output / "manifest.json", workflow


def test_record_scores_all_outcomes_and_rule_finishes_once(recording, capsys):
    cli, path, _, _ = recording
    assert cli("record") == 0
    data = measurement.read(path)
    run, = data["runs"]
    assert run["model"] == "claude-opus-4" and run["run_id"] == "wf-one"
    assert all(row["outcome"] == row["case"] for row in run["cases"])
    assert cli("rule", "--run", "wf-one") == 0
    assert "Score disappears." in capsys.readouterr().out
    original = path.read_bytes()
    assert cli("record") == 1
    assert cli("rule", "--case", "needs_ruling", "--outcome", "caught", "--note", " ") == 1
    assert path.read_bytes() == original
    assert cli("rule", "--case", "needs_ruling", "--outcome", "caught", "--note", "Names the missing score") == 0
    assert cli("rule", "--case", "needs_ruling", "--outcome", "missed", "--note", "Repeat") == 1
    row = measurement.read(path)["runs"][0]["cases"][2]
    assert row["ruled"] and row["note"] == "Names the missing score" and row["outcome"] == "caught"


@pytest.mark.parametrize("change", ["case rebuild", "prompt rebuild", "mcp", "missing tools",
                                    "missing result", "fallback", "different opus", "unrelated head"])
def test_void_runs_name_cases_and_write_nothing(recording, change, capsys):
    cli, path, manifest_path, workflow = recording
    manifest = measurement.read(manifest_path)
    case = manifest["cases"][0]
    journal_path = workflow / "journal.jsonl"
    rows = measurement.json_lines(journal_path)
    if change.endswith("rebuild"):
        manifest["built_at"] = "2026-01-03T00:00:00Z"
        if change == "prompt rebuild":
            for c in manifest["cases"]:
                c["prompt"] += " (new)"
        else:
            manifest["cases_fingerprint"] = "updated"
    elif change == "mcp":
        rows[1]["toolsUsed"].append("mcp__index")
    elif change == "missing tools":
        del rows[1]["toolsUsed"]
    elif change == "missing result":
        rows.pop(1)
    elif change == "unrelated head":
        case["head"] = "0" * 40
    else:
        transcript = workflow / "agent-0.jsonl"
        turns = measurement.json_lines(transcript)
        turns[-1]["message"]["model"] = "sonnet" if change == "fallback" else "other-opus"
        jsonl(transcript, turns)
    jsonl(journal_path, rows)
    measurement.write(manifest_path, manifest)
    assert cli("record") == 1
    error = capsys.readouterr().err
    assert "caught" in error
    if change.endswith("rebuild"):
        assert all(c["name"] in error for c in manifest["cases"])
    assert not path.exists()


def test_exact_prompt_and_criterion_are_required(recording):
    cli, path, _, workflow = recording
    transcript = workflow / "agent-0.jsonl"
    turns = measurement.json_lines(transcript)
    turns[0]["message"]["content"] += " "
    jsonl(transcript, turns)
    assert cli("record") == 1 and not path.exists()
    turns[0]["message"]["content"] = "Review caught"
    jsonl(transcript, turns)
    journal = workflow / "journal.jsonl"
    rows = measurement.json_lines(journal)
    rows[1]["result"]["criteria_verdicts"][0]["criterion"] += " "
    jsonl(journal, rows)
    assert cli("record") == 0
    assert measurement.read(path)["runs"][0]["cases"][0]["outcome"] == "needs_ruling"


def test_optional_criterion_grades_can_be_absent(recording):
    cli, path, _, workflow = recording
    journal = workflow / "journal.jsonl"
    rows = measurement.json_lines(journal)
    del rows[1]["result"]["criteria_verdicts"]
    jsonl(journal, rows)
    assert cli("record") == 0
    assert measurement.read(path)["runs"][0]["cases"][0]["outcome"] == "needs_ruling"


def harness_wrapped(prompt):
    computed = ("[Workflow harness — computed task] The task text below was computed by a script. "
                "The computed task text follows:\n" + "\n".join("  " + line for line in prompt.split("\n")))
    return [{"type": "user", "timestamp": "2026-01-02T00:00:00Z", "message": {"content": computed}},
            {"type": "assistant", "message": {"model": "claude-opus-4"}}]


@pytest.mark.parametrize("prompt, recorded", [
    ("Review caught", True),
    ("Review caught\n\nwith a blank line", False),
    ("Review something else", False),
])
def test_harness_wrapped_prompt_is_unwrapped_before_matching(recording, prompt, recorded):
    cli, path, _, workflow = recording
    jsonl(workflow / "agent-0.jsonl", harness_wrapped(prompt))
    assert cli("record") == (0 if recorded else 1)
    assert path.exists() == recorded


def test_harness_wrapped_prompt_with_an_unindented_line_is_void(recording):
    cli, path, _, workflow = recording
    turns = harness_wrapped("Review caught")
    turns[0]["message"]["content"] = turns[0]["message"]["content"].replace("  Review", "Review")
    jsonl(workflow / "agent-0.jsonl", turns)
    assert cli("record") == 1 and not path.exists()


def test_editor_shown_the_launching_request_is_void(recording, capsys):
    cli, path, _, workflow = recording
    relayed = {"type": "user", "timestamp": "2026-01-02T00:00:00Z", "message": {
        "content": "[Workflow harness — user request] The harness relays the request.\n"
                   "  <command-name>/measure-editor</command-name>"}}
    jsonl(workflow / "agent-0.jsonl", [relayed] + harness_wrapped("Review caught"))
    assert cli("record") == 1 and not path.exists()
    assert "launched the run" in capsys.readouterr().err

"""Replay small workflow journals through the public record and rule commands."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import editor_measure
import editor_results as measurement

CONTEXT_ROWS = Path(__file__).parent / "fixtures" / "blind_launch_context.json"
RUNNER_TOKEN = "5f0c2a9e7d31b846"
STARTED = "2026-01-02T00:00:00Z"


def jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def filled(value, places):
    if isinstance(value, str):
        for marker, path in places.items():
            value = value.replace(marker, path)
        return value
    if isinstance(value, dict):
        return {key: filled(item, places) for key, item in value.items()}
    if isinstance(value, list):
        return [filled(item, places) for item in value]
    return value


def editor_context(launch_folder, config_dir, prompt, started=STARTED):
    places = {"{launch_folder}": str(launch_folder), "{config_dir}": str(config_dir)}
    rows = filled(measurement.read(CONTEXT_ROWS), places)
    rows[0]["message"]["content"] = prompt
    rows[0]["timestamp"] = started
    return rows


def editor_turns(manifest, content):
    config_dir = os.environ["CLAUDE_CONFIG_DIR"]
    return editor_context(manifest["launch_folder"], config_dir, content) + [
        {"type": "assistant", "message": {"model": "claude-opus-4"}}]


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
    launch_folder = tmp_path / "checkouts/harbor-notes"
    tree = tmp_path / "checkout"
    tree.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    subprocess.run(["git", "-c", "user.name=Editor", "-c", "user.email=editor@example.org",
                    "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "writer"], cwd=tree, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tree, text=True).strip()
    manifest = {"built_at": "2026-01-01T00:00:00Z", "model": "opus", "cases": [],
                "prompt_fingerprint": "p", "cases_fingerprint": "c",
                "launch_folder": str(launch_folder), "runner_token": RUNNER_TOKEN,
                "instruction_files": [str(config / "CLAUDE.md"), str(launch_folder / "CLAUDE.md")],
                "forbidden_paths": [str(tmp_path / "main-checkout"), "~/Repos/main-checkout",
                                    str(config / "projects") + "/"],
                "launch_fingerprint": "launch-print"}
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
        jsonl(workflow / f"agent-{i}.jsonl", editor_turns(manifest, case["prompt"]))
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


def harness_wrapped(manifest_path, prompt):
    computed = ("[Workflow harness — computed task] The task text below was computed by a script. "
                "The computed task text follows:\n" + "\n".join("  " + line for line in prompt.split("\n")))
    return editor_turns(measurement.read(manifest_path), computed)


@pytest.mark.parametrize("prompt, recorded", [
    ("Review caught", True),
    ("Review caught\n\nwith a blank line", False),
    ("Review something else", False),
])
def test_harness_wrapped_prompt_is_unwrapped_before_matching(recording, prompt, recorded):
    cli, path, manifest_path, workflow = recording
    jsonl(workflow / "agent-0.jsonl", harness_wrapped(manifest_path, prompt))
    assert cli("record") == (0 if recorded else 1)
    assert path.exists() == recorded


def test_harness_wrapped_multiline_prompt_with_a_blank_line_is_recorded(recording):
    cli, path, manifest_path, workflow = recording
    prompt = "Review caught\n\n  Indented step\nLast line"
    manifest = measurement.read(manifest_path)
    manifest["cases"][0]["prompt"] = prompt
    measurement.write(manifest_path, manifest)
    jsonl(workflow / "agent-0.jsonl", harness_wrapped(manifest_path, prompt))
    assert cli("record") == 0
    assert measurement.read(path)["runs"][0]["cases"][0]["case"] == "caught"

def test_harness_wrapped_prompt_with_an_unindented_line_is_void(recording):
    cli, path, manifest_path, workflow = recording
    turns = harness_wrapped(manifest_path, "Review caught")
    turns[0]["message"]["content"] = turns[0]["message"]["content"].replace("  Review", "Review")
    jsonl(workflow / "agent-0.jsonl", turns)
    assert cli("record") == 1 and not path.exists()


def test_editor_shown_the_launching_request_is_void(recording, capsys):
    cli, path, manifest_path, workflow = recording
    relayed = {"type": "user", "timestamp": "2026-01-02T00:00:00Z", "message": {
        "content": "[Workflow harness — user request] The harness relays the request.\n"
                   "  <command-name>/measure-editor</command-name>"}}
    jsonl(workflow / "agent-0.jsonl", [relayed] + harness_wrapped(manifest_path, "Review caught"))
    assert cli("record") == 1 and not path.exists()
    assert "launched the run" in capsys.readouterr().err


def launch_scene(manifest_path, workflow):
    manifest = measurement.read(manifest_path)
    return {"launch": manifest["launch_folder"], "config": os.environ["CLAUDE_CONFIG_DIR"],
            "session": str(workflow.parents[2]), "main": manifest["forbidden_paths"][0],
            "token": manifest["runner_token"]}


def tool_use(tool_input):
    return {"type": "assistant", "message": {"model": "claude-opus-4", "content": [
        {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": tool_input}]}}


def tool_result(text):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "toolu_1", "content": [{"type": "text", "text": text}]}]}}


def context_row(rows, kind):
    row, = [r for r in rows if r.get("attachment", {}).get("type") == kind]
    return row


def started_in(folder):
    def change(rows, scene):
        environment = context_row(rows, "environment")
        environment["rendered"] = filled(environment["rendered"], {scene["launch"]: folder.format(**scene)})
        return rows
    return change


def without_starting_folder_line(rows, scene):
    environment = context_row(rows, "environment")
    rendered = environment["rendered"][0]
    rendered["content"] = rendered["content"].replace(f" - Primary working directory: {scene['launch']}\n", "")
    return rows


def with_extra_instruction_file(rows, scene):
    rendered = context_row(rows, "instructions")["rendered"][0]
    rendered["content"] += "\n\nContents of /srv/notes/CLAUDE.md (project instructions, checked into the codebase):\n\nNotes."
    return rows


def without_the_copied_instruction_file(rows, scene):
    rendered = context_row(rows, "instructions")["rendered"][0]
    header = f"Contents of {scene['launch']}/CLAUDE.md (project instructions, checked into the codebase):"
    assert header in rendered["content"]
    rendered["content"] = rendered["content"].replace(header, "")
    return rows


def without_instruction_lines(rows, scene):
    return [row for row in rows if row is not context_row(rows, "instructions")]


def with_git_status(rows, scene):
    status = {"type": "attachment", "rendered": [{"content": "gitStatus: Current branch: main\n\nStatus:\n?? notes.md"}]}
    return rows[:-1] + [status] + rows[-1:]


def with_context_line(line):
    def change(rows, scene):
        rendered = context_row(rows, "environment")["rendered"][0]
        rendered["content"] = rendered["content"].replace(" - Is a git repository", line.format(**scene) + "\n - Is a git repository")
        return rows
    return change


def then(build):
    def change(rows, scene):
        return rows + build(scene)
    return change


VOID_LAUNCHES = {
    "another starting folder": (
        started_in("/srv/elsewhere"), "the editor started in /srv/elsewhere, not in the launch folder"),
    "a folder that only begins with the launch folder's": (
        started_in("{launch}-old"), "-old, not in the launch folder"),
    "no starting-folder line": (
        without_starting_folder_line, "no line of the editor's context says which folder it started in"),
    "an extra instruction file": (
        with_extra_instruction_file, "the editor loaded instruction files the launch does not: /srv/notes/CLAUDE.md"),
    "a missing instruction file": (
        without_the_copied_instruction_file, "the editor did not load instruction files the launch does: "),
    "no instruction lines": (
        without_instruction_lines, "the editor's context lists no instruction files"),
    "a git status": (
        with_git_status, "the editor was shown a git status"),
    "a forbidden path in the context": (
        with_context_line(" - Additional working directories: {main}"), "the editor's context names "),
    "a forbidden absolute path in a tool input": (
        then(lambda s: [tool_use({"command": f"git -C {s['main']}/studio log -3"})]),
        "a tool input names "),
    "a forbidden home path in a tool input": (
        then(lambda s: [tool_use({"command": "ls ~/Repos/main-checkout"})]),
        "a tool input names ~/Repos/main-checkout, and editors must not touch ~/Repos/main-checkout"),
    "a read of the session's subagents folder": (
        then(lambda s: [tool_use({"file_path": f"{s['session']}/subagents/workflows/wf-one/agent-1.jsonl"})]),
        "/subagents/workflows/wf-one/agent-1.jsonl, and editors must not touch "),
    "a tool-results path that climbs into subagents": (
        then(lambda s: [tool_use({"command": f"cat {s['session']}/tool-results/../subagents/workflows/wf-one/journal.jsonl"})]),
        "/tool-results/../subagents/workflows/wf-one/journal.jsonl, and editors must not touch "),
    "a read of the subagents tool-results folder": (
        then(lambda s: [tool_use({"file_path": f"{s['session']}/subagents/tool-results/big-output.txt"})]),
        "/subagents/tool-results/big-output.txt, and editors must not touch "),
    "the runner token in a tool input": (
        then(lambda s: [tool_use({"command": f"grep -rl review {s['launch']}/.claude/{s['token']}.js"})]),
        f"a tool input names the runner {RUNNER_TOKEN}"),
    "the runner token in a tool result": (
        then(lambda s: [tool_use({"command": "ls -a .claude"}), tool_result(f"settings.json\n{s['token']}.js\n")]),
        f"a tool result shows the runner {RUNNER_TOKEN}"),
}


@pytest.mark.parametrize("void", list(VOID_LAUNCHES))
def test_a_case_whose_editor_could_see_the_measurement_is_void_and_named(recording, void, capsys):
    cli, path, manifest_path, workflow = recording
    scene = launch_scene(manifest_path, workflow)
    change, seen = VOID_LAUNCHES[void]
    transcript = workflow / "agent-0.jsonl"
    jsonl(transcript, change(measurement.json_lines(transcript), scene))

    assert cli("record") == 1
    error = capsys.readouterr().err
    assert re.search(r"\bcaught: [^;]*" + re.escape(seen), error), error
    assert not path.exists()


@pytest.mark.parametrize("line_ends", ["followed by further lines", "at the end of a text value"])
def test_a_replayed_blind_run_records_its_launch_and_claude_code_version(recording, line_ends):
    cli, path, manifest_path, workflow = recording
    scene = launch_scene(manifest_path, workflow)
    starting_line = f" - Primary working directory: {scene['launch']}"
    for transcript in workflow.glob("agent-*.jsonl"):
        rows = measurement.json_lines(transcript)
        environment = context_row(rows, "environment")
        content = environment["rendered"][0]["content"]
        assert starting_line + "\n - Is a git repository" in content
        if line_ends == "at the end of a text value":
            before, after = content.split(starting_line)
            environment["rendered"] = [{"content": before + starting_line}, {"content": after}]
        jsonl(transcript, rows)

    assert cli("record") == 0
    run, = measurement.read(path)["runs"]
    assert run["launch_fingerprint"] == "launch-print"
    assert run["claude_code_version"] == "2.1.332"


def test_claude_code_version_lists_each_distinct_version_and_is_null_when_no_row_has_one(recording):
    cli, path, _, workflow = recording
    transcript = workflow / "agent-1.jsonl"
    rows = measurement.json_lines(transcript)
    rows[-1]["version"] = "2.1.340"
    jsonl(transcript, rows)
    assert cli("record") == 0
    assert measurement.read(path)["runs"][0]["claude_code_version"] == "2.1.332, 2.1.340"

    path.unlink()
    for transcript in workflow.glob("agent-*.jsonl"):
        rows = measurement.json_lines(transcript)
        for row in rows:
            row.pop("version", None)
        jsonl(transcript, rows)
    journal = workflow.parent / "wf-two"
    shutil.copytree(workflow, journal)
    shutil.rmtree(workflow)
    assert cli("record") == 0
    assert measurement.read(path)["runs"][0]["claude_code_version"] is None


def test_a_main_checkout_path_in_a_tool_result_and_a_read_of_the_sessions_own_tool_results_are_not_void(recording):
    cli, path, manifest_path, workflow = recording
    scene = launch_scene(manifest_path, workflow)
    assert workflow == Path(scene["config"]) / "projects/project/session/subagents/workflows/wf-one"
    own_output = f"{scene['session']}/tool-results/toolu_9.txt"
    transcript = workflow / "agent-0.jsonl"
    rows = measurement.json_lines(transcript) + [
        tool_use({"file_path": own_output}),
        tool_result(f"Repository root: {scene['main']}\nSee ~/Repos/main-checkout/studio/README.md"),
    ]
    jsonl(transcript, rows)

    assert cli("record") == 0
    assert measurement.read(path)["runs"][0]["run_id"] == "wf-one"


def test_the_context_fixture_holds_no_personal_path_or_email():
    text = CONTEXT_ROWS.read_text(encoding="utf-8")
    assert "/Users/" not in text and "/home/" not in text
    emails = re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    assert emails and all(email.endswith("@example.com") for email in emails), emails

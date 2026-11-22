import json
import shutil
import subprocess

import pytest

import editor_results as measurement

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="the renderer runs in node")


def test_renders_pinned_prompt_and_unbuilt_runner_spawns_nothing():
    fixture = measurement.read(measurement.WORKFLOWS / "tests/fixtures/prompts-no-work-dir.json")
    rendered = measurement.node("render", [fixture])
    assert rendered["prompts"] == [fixture["editor_prompt"]]
    assert rendered["schema"]["type"] == "object" and rendered["model"] == "opus"
    runner = (measurement.DATASET / "measure-runner.js").read_text().removeprefix("export ")
    harness = "const run = new (Object.getPrototypeOf(async()=>{}).constructor)(" + json.dumps(runner) + "); run().then(v=>console.log(JSON.stringify(v)))"
    output = subprocess.check_output(["node", "-e", harness], text=True)
    assert json.loads(output) == {"measured": False, "reason": "not_built"}


def test_fingerprint_tracks_behavior_and_gate_source(tmp_path):
    source = (measurement.WORKFLOWS / "implementation-loop.js").read_text()
    script = tmp_path / "loop.js"
    knobs = measurement.settings()

    def fingerprint(code=source, **changes):
        script.write_text(code)
        return measurement.fingerprints(tmp_path, tmp_path, {**knobs, **changes}, script)["prompt_fingerprint"]

    expected = fingerprint()
    assert fingerprint("// A comment outside the gate.\n" + source) == expected
    for old, new in [
        ("You are the EDITOR", "You are the REVIEWER"), ("Default to deletion", "Prefer deletion"),
        ("cd there before you do anything else, and stay there.", "run commands from wherever your shell started."),
        ("const EDITOR_HANDOFF = {", "const EDITOR_HANDOFF = { description: 'Edited schema',"),
        ("const EDITOR_MODEL = 'opus'", "const EDITOR_MODEL = 'different'"),
        ("function unconfirmedCriteria(criteria, verdicts) {", "function unconfirmedCriteria(criteria, verdicts) { // revised"),
        ("function passesExitGate(editor, unconfirmed) {", "function passesExitGate(editor, unconfirmed) { // revised"),
    ]:
        assert old in source and fingerprint(source.replace(old, new)) != expected
    assert fingerprint(output_budget=knobs["output_budget"] + 10) != expected
    other_scope = "touched" if knobs["read_scope"] != "touched" else "touched+importers"
    assert fingerprint(read_scope=other_scope) != expected
    assert fingerprint(observe_command="capture-board") != expected

"""Exercise the headless transport through stdin/stdout, in a fresh working directory."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ADAPTER = Path(__file__).resolve().parents[1] / "forge_claude.mjs"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="portable Forge requires Node")
ENVELOPE = {"handoff": {"stage": "writer"}, "changes": [{"path": "sample", "blob": "a" * 40}]}
SECRET = "CREDENTIAL-TRANSCRIPT-SENTINEL"

# The stub substitutes this invocation's generated IDs in sanitized wire messages.
FAKE_CLI = r'''
import json, os, pathlib, sys
args = sys.argv[1:]
sid = args[args.index("--session-id") + 1]
init, turn = map(json.loads, sys.stdin.readlines())
assert init["request"]["subtype"] == "initialize"
assert turn["session_id"] == sid and turn["message"]["content"] == "build sample"
assert args[args.index("--json-schema") + 1] == '{"type":"object"}'
assert args[args.index("--permission-mode") + 1] == "acceptEdits"
assert "--no-session-persistence" in args and "--dangerously-skip-permissions" not in args
pathlib.Path("called.json").write_text(json.dumps(args))
print("CREDENTIAL-TRANSCRIPT-SENTINEL", file=sys.stderr)
for line in json.loads(os.environ["CLAUDE_FIXTURE"]):
    if isinstance(line, str):
        print(line)
        continue
    line.setdefault("session_id", sid)
    if line.get("type") == "control_response":
        line["response"].setdefault("request_id", init["request_id"])
    print(json.dumps(line))
sys.exit(int(os.environ["CLAUDE_EXIT"]))
'''

DRIVER = '''
const {runClaude} = await import(process.env.ADAPTER);
const execution = {completed:true, observed_models:["yesterday"]};
let result, error;
try {
  result = await runClaude({cwd:process.cwd(), prompt:process.env.ROLE_PROMPT,
                            schema:JSON.parse(process.env.ROLE_SCHEMA),
                            model:process.env.PIN || null, execution});
} catch (e) { error = e.message; }
console.log(JSON.stringify({result, error, execution}));
'''


def run(tmp_path, events, pin=None, exit_code=0, install=True):
    fake = tmp_path / "claude"
    if install:
        fake.write_text(f"#!{sys.executable}\n" + FAKE_CLI)
        fake.chmod(0o755)
    env = {**os.environ, "PATH": str(tmp_path), "ADAPTER": ADAPTER.as_uri(),
           "ROLE_PROMPT": "build sample", "ROLE_SCHEMA": '{"type":"object"}',
           "PIN": pin or "", "CLAUDE_EXIT": str(exit_code), "CLAUDE_FIXTURE": json.dumps(events)}
    proc = subprocess.run([NODE, "--input-type=module", "-e", DRIVER], cwd=tmp_path,
                          env=env, capture_output=True, text=True, check=True, timeout=10)
    assert SECRET not in proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def assistant(model, **fields):
    return {"type": "assistant", "parent_tool_use_id": None,
            "message": {"role": "assistant", "model": model, "stop_reason": "tool_use",
                        "content": [{"type": "text", "text": SECRET}]}, **fields}


def result(**fields):
    return {"type": "result", "subtype": "success", "is_error": False,
            "permission_denials": [], "structured_output": ENVELOPE, **fields}


def initialize(**fields):
    return {"type": "control_response", "response": {
        "subtype": "success", "response": {
            "account": {"email": SECRET},
            "models": [{"value": "sonnet", "resolvedModel": "claude-sonnet-5-5"},
                       {"value": "unused", "resolvedModel": SECRET}]}, **fields}}


def test_correlates_provider_alias_and_role_turns(tmp_path):
    default = "claude-sonnet-5-5"
    fallback = "claude-opus-5-5"
    reply = run(tmp_path, [
        initialize(), {"type": "system", "subtype": "init", "model": "initial-only"},
        assistant("other-session", session_id="other"), assistant("helper", parent_tool_use_id="tool"),
        assistant("other-agent", agent_id="subagent"), assistant("partial", aborted=True),
        assistant(default), {"type": "system", "subtype": "model_refusal_fallback",
                             "original_model": default, "fallback_model": fallback},
        assistant(fallback), result(modelUsage={SECRET: {"inputTokens": 1}}),
    ], pin="sonnet")
    assert reply["result"] == ENVELOPE
    execution = reply["execution"]
    assert execution == {"actual_runtime": "claude", "completed": True,
                         "observed_models": [default, fallback],
                         "reroutes": [{"from": default, "to": fallback}],
                         "confirmed_aliases": [{"alias": "sonnet", "model": default}],
                         "refused_commands": 0, "session_id": execution["session_id"]}
    args = json.loads((tmp_path / "called.json").read_text())
    assert args[args.index("--session-id") + 1] == execution["session_id"]
    assert args[args.index("--model") + 1] == "sonnet"


def test_default_model_and_older_stream_can_complete_with_unknown_identity(tmp_path):
    events = [initialize(request_id="uncorrelated"),
              {"type": "system", "subtype": "init", "model": "requested"},
              result(modelUsage={"initial-only": {"inputTokens": 77}})]
    first = run(tmp_path, events)
    second = run(tmp_path, events)
    assert first["result"] == ENVELOPE
    assert first["execution"]["observed_models"] == first["execution"]["confirmed_aliases"] == []
    assert first["execution"]["session_id"] != second["execution"]["session_id"]
    assert "--model" not in json.loads((tmp_path / "called.json").read_text())


def test_uncorrelated_initialization_cannot_confirm_a_requested_alias(tmp_path):
    reply = run(tmp_path, [initialize(request_id="different-request"),
                           assistant("claude-sonnet-5-5"), result()], pin="sonnet")
    assert reply["execution"]["observed_models"] == ["claude-sonnet-5-5"]
    assert reply["execution"]["confirmed_aliases"] == []


@pytest.mark.parametrize(("events", "exit_code", "error"), [
    ([assistant("<synthetic>", error="authentication_failed"), result(is_error=True)], 1, "authenticat"),
    ([assistant("<synthetic>", error="rate_limit"), result(is_error=True)], 1, "limit"),
    ([result(structured_output=None)], 0, "handoff"),
    ([result(session_id="other")], 0, "result"),
    ([result(), result()], 0, "result"),
    ([SECRET], 0, "stream"),
    ([result()], 3, "exit"),
])
def test_failures_do_not_publish_a_completed_identity(tmp_path, events, exit_code, error):
    reply = run(tmp_path, [assistant("claude-sonnet-5-5"), *events], exit_code=exit_code)
    assert error in reply["error"].lower()
    assert "result" not in reply
    assert not reply["execution"]["completed"]
    assert reply["execution"]["observed_models"] == []


def test_refused_commands_are_counted_without_failing_a_completed_role(tmp_path):
    refusals = [{"tool_name": "Bash", "tool_input": {"command": SECRET}}] * 2
    reply = run(tmp_path, [assistant("claude-sonnet-5-5"),
                           {"type": "system", "subtype": "permission_denied", "message": SECRET},
                           result(permission_denials=refusals)])
    assert reply["result"] == ENVELOPE
    assert reply["execution"]["completed"]
    assert reply["execution"]["refused_commands"] == 2


def test_refused_commands_are_counted_when_the_role_fails(tmp_path):
    reply = run(tmp_path, [assistant("claude-sonnet-5-5"),
                           result(structured_output=None, permission_denials=[{"tool_input": SECRET}])])
    assert "handoff" in reply["error"]
    assert not reply["execution"]["completed"]
    assert reply["execution"]["refused_commands"] == 1


def test_unavailable_executable_retains_unknown_actual_runtime(tmp_path):
    reply = run(tmp_path, [], install=False)
    assert "unavailable" in reply["error"]
    assert reply["execution"]["actual_runtime"] is None
    assert not reply["execution"]["completed"]


@pytest.mark.skipif(os.environ.get("STUDIO_LIVE_CLAUDE") != "1",
                    reason="set STUDIO_LIVE_CLAUDE=1 to use a signed-in Claude CLI")
def test_live_claude_edits_and_reports_git_blob(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    schema = {
        "type": "object", "required": ["handoff", "changes"],
        "properties": {
            "handoff": {"type": "object", "required": ["stage"],
                        "properties": {"stage": {"enum": ["writer"]}}},
            "changes": {"type": "array", "items": {"type": "object", "required": ["path", "blob"],
                        "properties": {"path": {"type": "string"}, "blob": {"type": "string"}}}},
        },
    }
    env = {**os.environ, "ADAPTER": ADAPTER.as_uri(), "ROLE_SCHEMA": json.dumps(schema), "PIN": "",
           "ROLE_PROMPT": "Create hello.txt containing hello and a newline. Use git hash-object -- "
                          "hello.txt for its blob ID. Report the file under changes and set "
                          "handoff.stage to writer. Leave git commits to the host."}
    proc = subprocess.run([NODE, "--input-type=module", "-e", DRIVER], cwd=tmp_path, env=env,
                          capture_output=True, text=True, check=True, timeout=300)
    reply = json.loads(proc.stdout)
    assert "error" not in reply, reply.get("error")
    assert reply["execution"]["completed"] and reply["execution"]["session_id"]
    assert (tmp_path / "hello.txt").read_text() == "hello\n"
    blob = subprocess.check_output(["git", "hash-object", "--", "hello.txt"], cwd=tmp_path, text=True)
    assert reply["result"] == {"handoff": {"stage": "writer"},
                               "changes": [{"path": "hello.txt", "blob": blob.strip()}]}

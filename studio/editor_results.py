"""Render the live editor, bind recorded workflows to their build, and evaluate measurements."""
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from impl_loop import load_loop_config, runtime_knobs

STUDIO = Path(__file__).resolve().parent
WORKFLOWS = STUDIO.parent / ".claude/workflows"
DATASET = STUDIO / "evals/forge_editor"
JUDGE = ".claude/workflows/implementation-loop.js::editorPrompt"
RULE = "A unit passes only when every acceptance criterion of its spec holds in the code."


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode="w", encoding="utf-8") as out:
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write("\n")
    os.replace(out.name, path)


@contextmanager
def exclusive(output):
    """Share a lock across builds, recording and rulings in this checkout."""
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def node(command, payload, script=None):
    args = ["node", str(WORKFLOWS / "tests/editor-prompt.mjs"), command]
    if script:
        args.append(str(script))
    result = subprocess.run(args, input=json.dumps(payload), capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr)
    return json.loads(result.stdout)


def cases_fingerprint(cases, patches):
    digest = hashlib.sha256()
    for path in sorted([*cases.glob("*.json"), *patches.glob("*.patch")], key=lambda p: p.name):
        digest.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def fingerprints(cases, patches, knobs, script=None):
    fixture = read(WORKFLOWS / "tests/fixtures/prompts-no-work-dir.json")
    # Every benchmark editor receives checkout instructions. A fixed path renders
    # those instructions and keeps the fingerprint reproducible across machines.
    unit = {**fixture["unit"], **knobs, "work_dir": "/studio/checkouts/reference",
            "acceptance_criteria": ["The profile is visible."]}
    rendered = node("render", [{"unit": unit, "writer": fixture["writer"]}], script)
    encoded = json.dumps(rendered, sort_keys=True, ensure_ascii=False).encode()
    return {"prompt_fingerprint": hashlib.sha256(encoded).hexdigest(),
            "cases_fingerprint": cases_fingerprint(cases, patches)}


def clear_builds(output):
    for manifest in output.glob("*/manifest.json"):
        shutil.rmtree(manifest.parent)


def runner_path(launch):
    return Path(launch["launch_folder"]) / ".claude" / f"{launch['runner_token']}.js"


def publish_build(rows, cases, patches, output, knobs, launch):
    units = []
    for row in rows:
        unit = {**knobs, "unit_id": row["unit_id"], "title": row["unit_id"].replace("_", " "),
                "work_dir": row["tree"], "test_command": row["test_command"],
                "acceptance_criteria": row["acceptance_criteria"]}
        units.append({"unit": unit, "writer": row.pop("writer")})
    rendered = node("render", units)
    for row, prompt in zip(rows, rendered["prompts"], strict=True):
        row["prompt"] = prompt
    built = {"trees": [{"name": row["name"], "prompt": row["prompt"]} for row in rows],
             "model": rendered["model"], "schema": rendered["schema"]}
    source = (DATASET / "measure-runner.js").read_text(encoding="utf-8")
    stamp = datetime.now(timezone.utc)
    destination = output / stamp.strftime("%Y%m%dT%H%M%S%fZ")
    manifest = {**fingerprints(cases, patches, knobs), "model": built["model"], **launch, "cases": rows}
    runner_path(launch).write_text(
        source.replace("name: 'unbuilt'", f"name: '{launch['runner_token']}'")
        .replace("const BUILT = null", "const BUILT = " + json.dumps(built)),
        encoding="utf-8")
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        staging = Path(temporary) / "build"
        staging.mkdir()
        manifest["built_at"] = datetime.now(timezone.utc).isoformat()
        write(staging / "manifest.json", manifest)
        staging.rename(destination)
    return destination


def settings():
    return runtime_knobs(load_loop_config())


def json_lines(path):
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp lacks a time zone")
    return result


RELAYED_REQUEST_HEADER = "[Workflow harness — user request]"
COMPUTED_TASK_HEADER = "[Workflow harness — computed task]"
COMPUTED_TASK_LEAD = "The computed task text follows:\n"
COMPUTED_TASK_INDENT = "  "


def user_text(row):
    content = row.get("message", {}).get("content")
    if isinstance(content, list) and len(content) == 1 and content[0].get("type") == "text":
        return content[0]["text"]
    return content


def task_prompt(first_user_row):
    text = user_text(first_user_row)
    if not isinstance(text, str) or not text.startswith(COMPUTED_TASK_HEADER):
        return text
    _, lead, task = text.partition(COMPUTED_TASK_LEAD)
    lines = task.split("\n")
    if not lead or not all(line.startswith(COMPUTED_TASK_INDENT) for line in lines):
        return None
    return "\n".join(line[len(COMPUTED_TASK_INDENT):] for line in lines)


def transcript_model(rows, case, manifest):
    if not rows or timestamp(rows[0]["timestamp"]) <= timestamp(manifest["built_at"]):
        raise ValueError("transcript predates this build")
    first = next((r for r in rows if r.get("type") == "user"), {})
    if str(user_text(first)).startswith(RELAYED_REQUEST_HEADER):
        raise ValueError("the editor was shown the request that launched the run; launch it headless")
    if task_prompt(first) != case["prompt"]:
        raise ValueError("first user prompt differs from the built prompt")
    models = {r["message"]["model"] for r in rows if r.get("type") == "assistant"}
    if len(models) != 1 or manifest["model"] not in next(iter(models)):
        raise ValueError("assistant model missing, mixed or outside the pinned family")
    return models.pop()


STARTING_FOLDER_LINE = "Primary working directory: "
INSTRUCTION_FILE_LINE = re.compile(r"Contents of (.+?) \(")
GIT_STATUS_LINE = "Current branch:"
PATH_IN_TEXT = re.compile(r"(?:~/|/)[^\s\"'`\\;|&()<>,:*?\[\]{}$=]*")


def decoded_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from decoded_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from decoded_strings(item)


def transcript_parts(rows):
    first_assistant = next((i for i, row in enumerate(rows) if row.get("type") == "assistant"), len(rows))
    context = "\n".join(text for row in rows[:first_assistant] for text in decoded_strings(row))
    actions = []
    results = []
    for row in rows:
        message = row.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and row.get("type") == "assistant":
                actions.append(json.dumps(block.get("input"), ensure_ascii=False))
            elif block.get("type") == "tool_result":
                results.extend(decoded_strings(block.get("content")))
    return context, "\n".join(actions), "\n".join(results)


def with_home_forms(paths):
    home = str(Path.home())
    listed = []
    for path in paths:
        forms = [path]
        if path.startswith(home + "/"):
            forms.append("~" + path[len(home):])
        for form in forms:
            if form not in listed:
                listed.append(form)
    return listed


def is_inside(path, folder):
    folder = posixpath.normpath(folder)
    return path == folder or path.startswith(folder + "/")


def path_into_measurement(text, forbidden_paths, exempt_folder):
    for seen in PATH_IN_TEXT.findall(text):
        normalized = posixpath.normpath(seen)
        if any(is_inside(normalized, exempt) for exempt in with_home_forms([str(exempt_folder)])):
            continue
        for forbidden in forbidden_paths:
            if is_inside(normalized, forbidden):
                return seen, forbidden
    return None


def launch_problem(rows, manifest, exempt_folder):
    context, actions, results = transcript_parts(rows)
    launch_folder = manifest["launch_folder"]
    lines = context.split("\n")
    if not any(line.endswith(STARTING_FOLDER_LINE + launch_folder) for line in lines):
        started_in = []
        for line in lines:
            if STARTING_FOLDER_LINE in line:
                folder = line.split(STARTING_FOLDER_LINE, 1)[1]
                if folder not in started_in:
                    started_in.append(folder)
        if started_in:
            return f"the editor started in {', '.join(started_in)}, not in the launch folder {launch_folder}"
        return (f"no line of the editor's context says which folder it started in "
                f"(looked for '{STARTING_FOLDER_LINE}{launch_folder}')")

    loaded = set(INSTRUCTION_FILE_LINE.findall(context))
    expected = set(manifest["instruction_files"])
    if not loaded:
        return "the editor's context lists no instruction files, so it cannot show it loaded exactly the launch's"
    extra = sorted(loaded - expected)
    missing = sorted(expected - loaded)
    differences = []
    if extra:
        differences.append(f"the editor loaded instruction files the launch does not: {', '.join(extra)}")
    if missing:
        differences.append(f"the editor did not load instruction files the launch does: {', '.join(missing)}")
    if differences:
        return ", and ".join(differences)

    if GIT_STATUS_LINE in context:
        return f"the editor was shown a git status (its context holds '{GIT_STATUS_LINE}')"

    for where, text in (("the editor's context", context), ("a tool input", actions)):
        found = path_into_measurement(text, manifest["forbidden_paths"], exempt_folder)
        if found:
            seen, forbidden = found
            return f"{where} names {seen}, and editors must not touch {forbidden}"

    token = manifest["runner_token"]
    if token in actions:
        return f"a tool input names the runner {token}"
    if token in results:
        return f"a tool result shows the runner {token}"
    return None


def claude_code_version(transcripts):
    versions = {row["version"] for rows in transcripts for row in rows if isinstance(row.get("version"), str)}
    return ", ".join(sorted(versions)) or None


def collect_journal(manifest, projects, used):
    names = {c["name"] for c in manifest["cases"]}
    rejected = []
    candidates = sorted(projects.glob("*/*/subagents/workflows/*/journal.jsonl"),
                        key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for path in candidates:
        run_id = path.parent.name
        if run_id in used:
            continue
        try:
            rows = json_lines(path)
        except (OSError, ValueError):
            continue
        starts = [r for r in rows if r.get("type") == "started"]
        if {r.get("label") for r in starts} != names:
            continue
        records = {}
        models = {}
        transcripts = []
        errors = []
        for case in manifest["cases"]:
            name = case["name"]
            try:
                start, = [r for r in starts if r["label"] == name]
                agent = start["agentId"]
                if not re.fullmatch(r"[\w-]+", agent) or sum(r.get("agentId") == agent for r in starts) != 1:
                    raise ValueError("invalid or repeated agent id")
                result, = [r for r in rows if r.get("type") == "result" and r.get("agentId") == agent]
                tools = result.get("toolsUsed")
                if not isinstance(tools, list) or any(not isinstance(t, str) or t.startswith("mcp__") for t in tools):
                    raise ValueError("missing or disallowed tools")
                editor = result.get("result")
                if not isinstance(editor, dict) or not isinstance(editor.get("tests", {}).get("passed"), bool):
                    raise ValueError("missing editor result")
                transcript = json_lines(path.parent / f"agent-{agent}.jsonl")
                models[name] = transcript_model(transcript, case, manifest)
                problem = launch_problem(transcript, manifest, path.parents[3] / "tool-results")
                if problem:
                    raise ValueError(problem)
                transcripts.append(transcript)
                records[name] = editor
            except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
                errors.append(f"{name}: {error}")
        if len(set(models.values())) > 1:
            errors.extend(f"{name}: mixed models ({model})" for name, model in models.items())
        if not errors:
            return run_id, next(iter(models.values())), records, claude_code_version(transcripts)
        rejected.extend(errors)
    raise ValueError("Void cases: " + "; ".join(rejected or sorted(names)))


def outcome(case, editor, gate, repaired):
    if case["kind"] == "clean":
        return "passed" if gate["passed"] else "false_alarm"
    number = case["breaks_criterion"]
    if number:
        target = case["acceptance_criteria"][number - 1]
        if any(v["criterion"] == target and v["verdict"] == "fail" for v in editor.get("criteria_verdicts", [])):
            return "caught"
    if repaired and editor["tests"]["passed"]:
        return "repaired"
    if not gate["passed"] or editor.get("unresolved_concerns"):
        return "needs_ruling"
    return "missed"


def totals(run):
    return Counter(row["outcome"] for row in run["cases"])


def read_results(path):
    return read(path) if path.exists() else {"judge": JUDGE, "mark": None, "runs": []}


def record(output, path, projects, probe):
    manifests = list(output.glob("*/manifest.json"))
    if len(manifests) != 1:
        raise ValueError("Build the cases before recording.")
    manifest = read(manifests[0])
    results = read_results(path)
    run_id, model, editors, version = collect_journal(manifest, projects, {r["run_id"] for r in results["runs"]})
    cases = manifest["cases"]
    moved = [c["name"] for c in cases if not (Path(c["tree"]) / ".git").is_dir() or subprocess.run(
        ["git", "-C", c["tree"], "merge-base", "--is-ancestor", c["head"], "HEAD"],
        capture_output=True).returncode]
    if moved:
        raise ValueError("Void cases with missing or unrelated HEAD: " + ", ".join(moved))
    gates = node("gate", [{"criteria": c["acceptance_criteria"], "editor": editors[c["name"]]} for c in cases])
    scored = []
    for case, gate in zip(cases, gates, strict=True):
        editor = editors[case["name"]]
        repaired = probe(case) if case["kind"] == "defect" else None
        scored.append({"case": case["name"], "kind": case["kind"], "source": case["source"],
                       "breaks_criterion": case.get("breaks_criterion"), "defect": case.get("defect"),
                       "outcome": outcome(case, editor, gate, repaired), "gate": gate, "editor": editor,
                       "probe_passed": repaired})
    run = {"run_id": run_id, "model": model, "measured_on": datetime.now(timezone.utc).isoformat(),
           "cases": scored, **{k: manifest[k] for k in ("prompt_fingerprint", "cases_fingerprint")},
           "launch_fingerprint": manifest["launch_fingerprint"], "claude_code_version": version}
    results["runs"].append(run)
    write(path, results)
    report(results, run)


def report(results, run):
    counts = totals(run)
    print(run["run_id"], dict(counts))
    if mark := results["mark"]:
        print(f"Missed {counts['missed']}/{mark['max_missed']}, false alarms {counts['false_alarm']}/{mark['max_false_alarms']}")
    for key in ("source", "breaks_criterion"):
        groups = {}
        for row in run["cases"]:
            if row["kind"] == "defect":
                group = row[key] if key == "source" else ("criterion" if row[key] else "no criterion")
                groups.setdefault(group, Counter())[row["outcome"]] += 1
        print(key, {group: dict(count) for group, count in groups.items()})
    catches = Counter("flagged" if not r["gate"]["passed"] else "unflagged" for r in run["cases"]
                      if r["outcome"] in ("caught", "repaired"))
    print("Catches by exit gate", dict(catches))
    previous = next((r for r in reversed(results["runs"][:results["runs"].index(run)])
                     if all(r[k] == run[k] for k in ("prompt_fingerprint", "cases_fingerprint"))), None)
    if previous:
        prior = {r["case"]: r["outcome"] for r in previous["cases"]}
        changed = [r["case"] for r in run["cases"] if prior.get(r["case"]) != r["outcome"]]
        print(f"Spread from {previous['run_id']}: {len(changed)}", ", ".join(changed))


def rule(path, run_id, name, verdict, note):
    results = read_results(path)
    run = next((r for r in reversed(results["runs"]) if not run_id or r["run_id"] == run_id), None)
    if run is None:
        raise ValueError("No matching run.")
    pending = {r["case"]: r for r in run["cases"] if r["outcome"] == "needs_ruling"}
    if name is None and verdict is None and note is None:
        for key, row in pending.items():
            print(key, row["defect"], json.dumps(row["editor"], ensure_ascii=False))
    else:
        if name not in pending or verdict not in ("caught", "missed") or not (note or "").strip():
            raise ValueError("Choose an unruled case, caught or missed, and a nonempty note.")
        pending[name].update(outcome=verdict, ruled=True, note=note.strip())
        write(path, results)
    report(results, run)

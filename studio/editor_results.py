"""Render the live editor, bind recorded workflows to their build, and evaluate measurements."""
import hashlib
import json
import os
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
    unit = {**fixture["unit"], **knobs, "acceptance_criteria": ["The profile is visible."]}
    rendered = node("render", [{"unit": unit, "writer": fixture["writer"]}], script)
    encoded = json.dumps(rendered, sort_keys=True, ensure_ascii=False).encode()
    return {"prompt_fingerprint": hashlib.sha256(encoded).hexdigest(),
            "cases_fingerprint": cases_fingerprint(cases, patches)}


def clear_builds(output):
    for manifest in output.glob("*/manifest.json"):
        shutil.rmtree(manifest.parent)


def publish_build(rows, cases, patches, output, knobs):
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
    manifest = {**fingerprints(cases, patches, knobs), "model": built["model"], "cases": rows}
    with tempfile.TemporaryDirectory(dir=output) as temporary:
        staging = Path(temporary) / "build"
        staging.mkdir()
        (staging / "measure-runner.js").write_text(
            source.replace("const BUILT = null", "const BUILT = " + json.dumps(built)), encoding="utf-8")
        manifest["built_at"] = datetime.now(timezone.utc).isoformat()
        write(staging / "manifest.json", manifest)
        staging.rename(destination)
    print(f"Runner: {destination / 'measure-runner.js'}")
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


def transcript_model(rows, case, manifest):
    if not rows or timestamp(rows[0]["timestamp"]) <= timestamp(manifest["built_at"]):
        raise ValueError("transcript predates this build")
    first = next((r for r in rows if r.get("type") == "user"), {})
    content = first.get("message", {}).get("content")
    if isinstance(content, list) and len(content) == 1 and content[0].get("type") == "text":
        content = content[0]["text"]
    if content != case["prompt"]:
        raise ValueError("first user prompt differs from the built prompt")
    models = {r["message"]["model"] for r in rows if r.get("type") == "assistant"}
    if len(models) != 1 or manifest["model"] not in next(iter(models)):
        raise ValueError("assistant model missing, mixed or outside the pinned family")
    return models.pop()


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
                records[name] = editor
            except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
                errors.append(f"{name}: {error}")
        if len(set(models.values())) > 1:
            errors.extend(f"{name}: mixed models ({model})" for name, model in models.items())
        if not errors:
            return run_id, next(iter(models.values())), records
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
    run_id, model, editors = collect_journal(manifest, projects, {r["run_id"] for r in results["runs"]})
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
           "cases": scored, **{k: manifest[k] for k in ("prompt_fingerprint", "cases_fingerprint")}}
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

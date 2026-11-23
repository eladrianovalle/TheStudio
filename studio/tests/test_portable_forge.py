"""Run the public CLI against real repositories, with provider-free planning."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from install import SOURCE_FILES


STUDIO = Path(__file__).resolve().parents[1]


def command(cwd, *args, **kwargs):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, **kwargs)


@pytest.fixture
def project(tmp_path):
    command(tmp_path, 'git', 'init', '-b', 'main', check=True)
    command(tmp_path, 'git', 'config', 'user.email', 'studio@example.test', check=True)
    command(tmp_path, 'git', 'config', 'user.name', 'Studio', check=True)
    config = tmp_path / '.studio'
    config.mkdir()
    (config / 'implementation_loop.toml').write_text('[gate]\ntest_command="true"\n')
    specs = config / 'specs'
    specs.mkdir()
    (specs / 'demo.md').write_text('---\nstatus: approved\n---\n## Build Plan\n'
                                  '### 1. `demo_unit` — Show a demo\n- [ ] Prints **demo**.\n')
    command(tmp_path, 'git', 'add', '.', check=True)
    command(tmp_path, 'git', 'commit', '-qm', 'fixture', check=True)
    return tmp_path


def cli(repo, *args, entry=None):
    return command(repo, sys.executable, str(entry or STUDIO / 'run_phase.py'), 'forge', *args,
                   env={k: v for k, v in os.environ.items() if k != 'STUDIO_ARTIFACT_ROOT'})


@pytest.mark.parametrize('installed', [True, False])
def test_plan_uses_target_layout_and_preserves_tree(project, installed):
    import shutil
    entry = STUDIO / 'run_phase.py'
    if installed:
        source = project / '.studio/source'
        for name in SOURCE_FILES:
            dest = source / name
            dest.parent.mkdir(exist_ok=True, parents=True)
            shutil.copyfile(STUDIO / name, dest)
        entry = source / 'run_phase.py'
    else:
        (project / '.studio/specs').rename(project / 'specs')
    before = sorted(project.rglob('*'))
    r = cli(project, '--spec', 'demo', '--plan', '--editor-runtime', 'claude', '--writer-model', 'w', entry=entry)
    assert r.returncode == 0, r.stderr
    plan = json.loads(r.stdout)
    assert plan['branch'] == 'impl/demo_unit'
    assert plan['acceptance_criteria'] == ['Prints **demo**.']
    assert plan['roles'] == {'writer': {'runtime': 'codex', 'model': 'w'}, 'editor': {'runtime': 'claude', 'model': None}}
    assert sorted(project.rglob('*')) == before
    assert command(project, 'git', 'branch', '--show-current').stdout.strip() == 'main'


@pytest.mark.parametrize(('spec', 'expected'), [(None, 'missing file'), ('', 'no Build Plan'),
    ('## Build Plan\n### 1. `foo` X\n### 2. `bar` Y', 'ambiguous unit'),
    ('## Build Plan\n### 1. `foo` X\n', 'empty criteria list')])
def test_invalid_specs_stop_before_dispatch(project, spec, expected):
    path = project / 'bad.md'
    if spec is not None:
        path.write_text('---\nstatus: approved\n---\n' + spec)
    r = cli(project, '--spec', str(path))
    assert r.returncode and expected in r.stderr


def test_workflow_generation_and_historical_editor_profile():
    import generate_forge
    assert generate_forge.render() == generate_forge.WORKFLOW.read_text()
    result = command(STUDIO, sys.executable, 'editor_measure.py', 'fingerprint', check=True)
    assert json.loads(result.stdout)['prompt_fingerprint'] == (
        '655f2fc215367952644394a5abdccfd8a490a2021d0311507ee9c90a46a04e8e'
    )


def test_existing_target_at_different_commit_refuses_before_dispatch(project):
    command(project, 'git', 'branch', 'other', check=True)
    command(project, 'git', 'commit', '--allow-empty', '-qm', 'new head', check=True)
    r = cli(project, 'Build a demo', '--branch', 'other')
    assert r.returncode and 'different HEAD' in r.stdout
    assert command(project, 'git', 'branch', '--show-current').stdout.strip() == 'main'


def test_missing_selected_editor_is_reported_before_writer(project, tmp_path_factory, monkeypatch):
    import shutil
    binaries = tmp_path_factory.mktemp('bin')
    for name in ('git', 'node'):
        (binaries / name).symlink_to(shutil.which(name))
    sentinel = binaries / 'writer-called'
    codex = binaries / 'codex'
    codex.write_text(f'#!/bin/sh\ntouch "{sentinel}"\n')
    codex.chmod(0o755)
    monkeypatch.setenv('PATH', str(binaries))
    r = cli(project, 'Build a demo', '--editor-runtime', 'claude')
    state = json.loads(r.stdout)
    assert r.returncode and state['failed_stage'] == 'editor'
    assert state['roles']['writer']['status'] == 'skipped'
    assert not sentinel.exists()


def test_missing_writer_is_stage_scoped(project, tmp_path_factory, monkeypatch):
    import shutil
    binaries = tmp_path_factory.mktemp('bin')
    for name in ('git', 'node'):
        (binaries / name).symlink_to(shutil.which(name))
    monkeypatch.setenv('PATH', str(binaries))
    r = cli(project, 'Build a demo')
    state = json.loads(r.stdout)
    assert r.returncode and state['failed_stage'] == 'writer'
    assert state['roles']['editor']['status'] == 'skipped'
    assert 'executable missing' in state['error']


def test_draft_acknowledgement_and_legacy_plan_entry(project):
    path = project / 'draft.md'
    path.write_text('---\nstatus: draft\n---\n## Build Plan\n1. **\x60old_unit\x60 — Older**\n'
                    '   - [ ] Retains the original text.\n2. **\x60next_one\x60**\n - [ ] Another.\n')
    args = ['--plan', '--spec', str(path), '--unit', 'old_unit']
    assert '--allow-draft' in cli(project, *args).stderr
    r = cli(project, *args, '--allow-draft')
    assert json.loads(r.stdout)['acceptance_criteria'] == ['Retains the original text.']


def test_extensionless_path_preserves_wrapped_criterion(project):
    spec = project / '.studio/specs/demo.md'
    spec.write_text(spec.read_text().replace('Prints **demo**.',
                                             'Prints **demo**\n  followed by a newline.'))
    r = cli(project, '--spec', '.studio/specs/demo', '--plan')
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)['acceptance_criteria'] == ['Prints **demo** followed by a newline.']


@pytest.mark.parametrize(('selection', 'writer_runtime', 'editor_runtime'), [
    ([], 'codex', 'codex'),
    (['--runtime', 'claude'], 'claude', 'claude'),
    (['--runtime', 'claude', '--writer-runtime', 'codex'], 'codex', 'claude'),
    (['--runtime', 'claude', '--editor-runtime', 'codex'], 'claude', 'codex'),
])
def test_plan_resolves_role_overrides_independently(project, selection, writer_runtime, editor_runtime):
    r = cli(project, 'Build a demo', '--plan', '--writer-model', 'w', '--editor-model', 'e', *selection)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)['roles'] == {
        'writer': {'runtime': writer_runtime, 'model': 'w'},
        'editor': {'runtime': editor_runtime, 'model': 'e'},
    }


CLAUDE_FORGE_FIXTURE = r'''
import json, os, pathlib, re, subprocess, sys

args = sys.argv[1:]
init, turn = map(json.loads, sys.stdin.readlines())
sid = turn["session_id"]
prompt = turn["message"]["content"]
pin = args[args.index("--model") + 1] if "--model" in args else None
stage = "writer" if "You are the WRITER" in prompt else "editor"
assert "--no-session-persistence" in args and sid == args[args.index("--session-id") + 1]
assert "Bash(true)" in args
secret = "PRIVATE-CREDENTIAL-TRANSCRIPT"
print(secret, file=sys.stderr)

def send(kind, **fields):
    print(json.dumps({"session_id": sid, "type": kind, **fields}))

def git(*args):
    return subprocess.check_output(["git", "-C", os.getcwd(), *args], text=True).strip()

def assistant(model, **fields):
    send("assistant", parent_tool_use_id=None, message={
        "role": "assistant", "model": model, "content": [{"type": "text", "text": secret}],
    }, **fields)

mode = os.environ.get("CLAUDE_FORGE_FIXTURE_MODE")
if stage == "editor" and mode == "denied":
    assistant("<synthetic>", error="authentication_failed")
    send("result", subtype="error", is_error=True, result=secret)
    sys.exit(1)
if mode != "unknown":
    assistant(pin or "claude-default")
if stage == "editor" and mode == "conflict":
    assistant("claude-other")
if stage == "editor" and mode == "reroute":
    send("system", subtype="model_refusal_fallback", original_model=pin, fallback_model="claude-other")

changes = []
handoff = {"stage": stage, "unit_id": "demo_unit", "files_touched": [],
           "tests": {"command": "true", "passed": True, "exit_code": 0}}
if stage == "writer":
    assert "Bash(git -C " in " ".join(args) and "rev-parse --short HEAD)" in " ".join(args)
    if not pathlib.Path("hello.txt").exists():
        pathlib.Path("hello.txt").write_text("demo")
        changes = [{"path": "hello.txt", "blob": git("hash-object", "--", "hello.txt")}]
    sha = git("rev-parse", "HEAD")
    handoff.update(base_sha=sha, writer_sha=sha, files_touched=[c["path"] for c in changes], mvi_claimed=True,
                   mutation_check={"performed": False, "reason": "not_configured"})
else:
    assert git("log", "-1", "--format=%s") == "writer: demo_unit"
    assert "Writer handoff:" in prompt and "Prints **demo**." in prompt
    assert any(re.fullmatch(r"Bash\(git -C .+ diff [0-9a-f]+\.\.[0-9a-f]+\)", a) for a in args)
    if mode in {"conflict", "reroute"}:
        pathlib.Path("hello.txt").write_text("editor edit")
        changes = [{"path": "hello.txt", "blob": git("hash-object", "--", "hello.txt")}]
        handoff["files_touched"] = ["hello.txt"]
    handoff.update(mvi_verdict=True, edits="Reviewed", reverted=False, committed=False,
                   criteria_verdicts=[{"criterion": "Prints **demo**.", "verdict": "pass",
                                       "evidence": "Read hello.txt at the tested checkpoint."}])
send("result", subtype="success", is_error=False, result=secret,
     modelUsage={secret: {}}, structured_output={"handoff": handoff, "changes": changes})
'''


@pytest.fixture
def claude_only(tmp_path_factory, monkeypatch):
    import shutil
    if not shutil.which('node'):
        pytest.skip('portable Forge requires Node')
    binaries = tmp_path_factory.mktemp('claude-bin')
    for name in ('git', 'node'):
        (binaries / name).symlink_to(shutil.which(name))
    claude = binaries / 'claude'
    claude.write_text(f'#!{sys.executable}\n' + CLAUDE_FORGE_FIXTURE)
    claude.chmod(0o755)
    monkeypatch.setenv('PATH', str(binaries))


def read_attempt(project, run):
    assert 'PRIVATE-CREDENTIAL-TRANSCRIPT' not in run.stdout + run.stderr
    state = json.loads(run.stdout)
    raw = Path(state['record']).read_text()
    assert 'PRIVATE-CREDENTIAL-TRANSCRIPT' not in raw
    assert json.loads(raw) == state
    assert command(project, 'git', 'rev-parse', 'HEAD').stdout.strip() == state['last_verified_sha']
    return state


def test_installed_claude_only_build_and_retry(project, claude_only, monkeypatch):
    import shutil
    source = project / '.studio/source'
    for name in SOURCE_FILES:
        dest = source / name
        dest.parent.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(STUDIO / name, dest)
    command(project, 'git', 'add', '.', check=True)
    command(project, 'git', 'commit', '-qm', 'install', check=True)
    args = ('--spec', 'demo', '--runtime', 'claude')
    entry = source / 'run_phase.py'
    run = cli(project, *args, '--writer-model', 'writer-pin', '--editor-model', 'editor-pin', entry=entry)
    assert run.returncode == 0, run.stdout + run.stderr
    first = read_attempt(project, run)
    assert first['result']['criteriaVerdicts'][0]['verdict'] == 'pass'
    assert first['roles']['writer']['session_id'] != first['roles']['editor']['session_id']
    for role, record in first['roles'].items():
        assert record['requested_runtime'] == record['actual_runtime'] == 'claude'
        assert record['observed_models'] == [record['requested_model']] == [f'{role}-pin']
        assert record['host_test']['passed']
    monkeypatch.setenv('CLAUDE_FORGE_FIXTURE_MODE', 'unknown')
    run = cli(project, *args, '--writer-model', 'writer-pin', entry=entry)
    assert run.returncode != 0
    retry = read_attempt(project, run)
    assert retry['failed_stage'] == 'writer'
    assert 'Unverified model pin' in retry['error']
    assert retry['last_verified_sha'] == first['last_verified_sha']
    assert retry['attempt'] != first['attempt']
    assert retry['roles']['writer']['session_id'] != first['roles']['writer']['session_id']
    assert retry['roles']['writer']['observed_models'] == []
    assert retry['roles']['editor'] == {
        'requested_runtime': 'claude', 'requested_model': None, 'actual_runtime': None,
        'session_id': None, 'observed_models': [], 'confirmed_aliases': [], 'reroutes': [],
        'completed': False, 'status': 'skipped',
    }
    assert json.loads(Path(first['record']).read_text()) == first


@pytest.mark.parametrize(('mode', 'error'), [
    ('denied', 'authentication_failed'), ('conflict', 'Unverified model pin'), ('reroute', 'Unverified model pin'),
])
def test_claude_editor_failure_preserves_writer_checkpoint(project, claude_only, monkeypatch, mode, error):
    monkeypatch.setenv('CLAUDE_FORGE_FIXTURE_MODE', mode)
    run = cli(project, '--spec', '.studio/specs/demo.md', '--runtime', 'claude', '--editor-model', 'editor-pin')
    assert run.returncode != 0
    state = read_attempt(project, run)
    assert state['failed_stage'] == 'editor' and error in state['error']
    assert state['roles']['editor']['status'] == 'failed'
    assert state['roles']['writer']['status'] == 'completed'
    assert command(project, 'git', 'log', '-1', '--format=%s').stdout.strip() == 'writer: demo_unit'
    assert (project / 'hello.txt').read_text() == 'demo'

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
    assert plan['roles'] == {'writer': {'runtime': 'claude', 'model': 'w'}, 'editor': {'runtime': 'claude', 'model': None}}
    assert sorted(project.rglob('*')) == before
    assert command(project, 'git', 'branch', '--show-current').stdout.strip() == 'main'


def install_source(project):
    import shutil
    source = project / '.studio/source'
    for name in SOURCE_FILES:
        dest = source / name
        dest.parent.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(STUDIO / name, dest)
    return source / 'run_phase.py'


@pytest.mark.parametrize('spelling', ['demo', 'demo.md'])
@pytest.mark.parametrize('layout', ['installed with top-level specs', 'tracked specs without the snapshot'])
def test_a_slug_resolves_from_whichever_specs_folder_holds_it(project, layout, spelling):
    entry = STUDIO / 'run_phase.py'
    if layout == 'installed with top-level specs':
        entry = install_source(project)
        (project / '.studio/specs').rename(project / 'specs')
    r = cli(project, '--spec', spelling, '--plan', entry=entry)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)['acceptance_criteria'] == ['Prints **demo**.']


@pytest.mark.parametrize('spelling', ['demo', 'demo.md'])
def test_a_slug_found_in_both_specs_folders_is_refused(project, spelling):
    (project / 'specs').mkdir()
    (project / 'specs/demo.md').write_text((project / '.studio/specs/demo.md').read_text())
    r = cli(project, '--spec', spelling, '--plan')
    assert r.returncode
    assert 'ambiguous spec' in r.stderr
    assert '.studio/specs/demo.md' in r.stderr and ' specs/demo.md' in r.stderr


def config_digest(project):
    import hashlib
    return hashlib.sha256((project / '.studio/implementation_loop.toml').read_bytes()).hexdigest()


@pytest.mark.parametrize('configured', ['', 'test_command = ""\n', 'test_command = "  "\n'])
def test_the_test_fallback_supplies_a_test_command_the_config_leaves_blank(project, configured):
    (project / '.studio/implementation_loop.toml').write_text(f'[gate]\n{configured}require_mutation_check = false\n')
    r = cli(project, '--spec', 'demo', '--test', 'make quick', '--plan')
    assert r.returncode == 0, r.stderr
    plan = json.loads(r.stdout)
    assert plan['test_command'] == 'make quick'
    assert plan['gate'] == {'test_command': 'make quick', 'suites': {},
                            'gate_config': '.studio/implementation_loop.toml',
                            'gate_config_sha256': config_digest(project)}


def test_the_configured_test_command_freezes_into_the_gate_and_test_only_shapes_the_in_loop_run(project):
    declare_web_suite(project, 'npm --prefix web run check')
    r = cli(project, '--spec', 'demo', '--test', 'make quick', '--plan')
    assert r.returncode == 0, r.stderr
    plan = json.loads(r.stdout)
    assert plan['test_command'] == 'make quick'
    assert plan['gate'] == {
        'test_command': 'true',
        'suites': {'web': {'command': 'npm --prefix web run check', 'paths': ['web/']}},
        'gate_config': '.studio/implementation_loop.toml',
        'gate_config_sha256': config_digest(project),
    }


def test_without_test_the_plan_runs_the_configured_command_in_loop(project):
    r = cli(project, '--spec', 'demo', '--plan')
    assert r.returncode == 0, r.stderr
    plan = json.loads(r.stdout)
    assert plan['test_command'] == plan['gate']['test_command'] == 'true'


def test_the_loader_only_falls_back_when_the_config_names_no_test_command(tmp_path):
    from impl_loop import load_loop_config
    configured = tmp_path / 'configured.toml'
    configured.write_text('[gate]\ntest_command = "pytest -q"\nrequire_mutation_check = false\n')
    blank = tmp_path / 'blank.toml'
    blank.write_text('[gate]\nrequire_mutation_check = false\n')
    assert load_loop_config(configured, test_command_fallback='true').test_command == 'pytest -q'
    assert load_loop_config(blank, test_command_fallback='true').test_command == 'true'


def declare_web_suite(project, web_command):
    (project / 'web').mkdir(exist_ok=True)
    (project / 'web/page.txt').write_text('app\n')
    (project / '.studio/implementation_loop.toml').write_text(
        f'[gate]\ntest_command = "true"\nrequire_mutation_check = false\n'
        f'[gate.suites.web]\ncommand = "{web_command}"\npaths = ["web/"]\n')
    command(project, 'git', 'add', '.', check=True)
    command(project, 'git', 'commit', '-qm', 'declare the web suite', check=True)


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
    r = cli(project, 'Build a demo', '--writer-runtime', 'codex', '--editor-runtime', 'claude')
    state = json.loads(r.stdout)
    assert r.returncode and state['failed_stage'] == 'editor'
    assert state['roles']['writer']['status'] == 'skipped'
    assert not sentinel.exists()


@pytest.mark.parametrize('record', ['unchecked', 'not json', 'missing fields'])
def test_an_unchecked_native_launch_refuses_the_portable_run(project, tmp_path_factory, monkeypatch, record):
    import shutil
    from impl_loop import open_loop_record
    record_file = project / '.git' / 'studio-forge.json'
    if record == 'unchecked':
        base = command(project, 'git', 'rev-parse', 'HEAD').stdout.strip()
        open_loop_record(project, unit_id='native_unit', branch='impl/native_unit', base_sha=base,
                         test_command='true', pack_check=None, suites={}, gate_config=None)
    elif record == 'not json':
        record_file.write_text('not json')
    else:
        record_file.write_text(json.dumps({'checked_at': ''}))
    binaries = tmp_path_factory.mktemp('bin')
    for name in ('git', 'node'):
        (binaries / name).symlink_to(shutil.which(name))
    sentinel = binaries / 'role-called'
    codex = binaries / 'codex'
    codex.write_text(f'#!/bin/sh\ntouch "{sentinel}"\n')
    codex.chmod(0o755)
    monkeypatch.setenv('PATH', str(binaries))
    r = cli(project, 'Build a demo', '--runtime', 'codex')
    state = json.loads(r.stdout)
    assert r.returncode and state['failed_stage'] == 'preflight'
    assert state['error'].startswith('unchecked-loop' if record == 'unchecked' else 'unreadable-record')
    if record == 'unchecked':
        assert '--check --work-dir' in state['error']
    assert not sentinel.exists()
    assert command(project, 'git', 'branch', '--show-current').stdout.strip() == 'main'
    assert record_file.exists()


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
    ([], 'claude', 'claude'),
    (['--runtime', 'codex'], 'codex', 'codex'),
    (['--writer-runtime', 'codex'], 'codex', 'claude'),
    (['--editor-runtime', 'codex'], 'claude', 'codex'),
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
assert "Bash(true)" in args or mode == "breaks"
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
    assert any(re.fullmatch(r"Bash\(git -C .+ rev-parse HEAD\)", a) for a in args)
    assert any(re.fullmatch(r"Bash\(git -C .+ hash-object -- \*\)", a) for a in args)
    if not pathlib.Path("hello.txt").exists():
        pathlib.Path("hello.txt").write_text("demo")
        changes = [{"path": "hello.txt", "blob": git("hash-object", "--", "hello.txt")}]
    if mode == "unity":
        pathlib.Path("Player.cs.meta").write_text("fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n")
        pathlib.Path("sound.wav").write_bytes(b"RIFF$\0\0\0WAVEfmt \x10\0\0\0\x01\0\x01\0D\xac\0\0")
        changes += [{"path": p, "blob": git("hash-object", "--", p)} for p in ("Player.cs.meta", "sound.wav")]
    edited = []
    if mode in {"web", "tamper"}:
        pathlib.Path("web/page.txt").write_text("broken")
        edited.append("web/page.txt")
    if mode == "tamper":
        pathlib.Path(".studio/source/gate_routes.py").write_text(
            'print(\'{"runs": [], "unclaimed": [], "config_changed": false}\')\n')
        edited.append(".studio/source/gate_routes.py")
    if mode == "config":
        config = pathlib.Path(".studio/implementation_loop.toml")
        config.write_text(config.read_text() + "static_checks = []\n")
        edited.append(".studio/implementation_loop.toml")
    changes += [{"path": p, "blob": git("hash-object", "--", p)} for p in edited]
    sha = git("rev-parse", "HEAD")
    handoff.update(base_sha=sha, writer_sha=sha, files_touched=[c["path"] for c in changes], mvi_claimed=True,
                   mutation_check={"performed": False, "reason": "not_configured"})
else:
    assert git("log", "-1", "--format=%s") == "writer: demo_unit"
    assert "Writer handoff:" in prompt and "Prints **demo**." in prompt
    assert any(re.fullmatch(r"Bash\(git -C .+ diff [0-9a-f]+\.\.[0-9a-f]+\)", a) for a in args)
    if mode in {"conflict", "reroute", "breaks"}:
        pathlib.Path("hello.txt").write_text("editor edit")
        changes = [{"path": "hello.txt", "blob": git("hash-object", "--", "hello.txt")}]
        handoff["files_touched"] = ["hello.txt"]
    handoff.update(mvi_verdict=True, edits="Reviewed", reverted=False, committed=False,
                   criteria_verdicts=[{"criterion": "Prints **demo**.", "verdict": "pass",
                                       "evidence": "Read hello.txt at the tested checkpoint."}])
refusals = [{"tool_name": "Bash", "tool_input": {"command": secret}}] if mode == "refused" else []
send("result", subtype="success", is_error=False, result=secret, permission_denials=refusals,
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


def test_claude_roles_that_work_around_a_refused_command_still_deliver(project, claude_only, monkeypatch):
    monkeypatch.setenv('CLAUDE_FORGE_FIXTURE_MODE', 'refused')
    run = cli(project, '--spec', '.studio/specs/demo.md', '--runtime', 'claude')
    assert run.returncode == 0, run.stdout + run.stderr
    state = read_attempt(project, run)
    assert state['result']['criteriaVerdicts'][0]['verdict'] == 'pass'
    for record in state['roles'].values():
        assert record['completed'] and record['refused_commands'] == 1


def test_unity_metadata_and_binary_assets_pass_the_writer_comment_gate(project, claude_only, monkeypatch):
    monkeypatch.setenv('CLAUDE_FORGE_FIXTURE_MODE', 'unity')
    run = cli(project, '--spec', '.studio/specs/demo.md', '--runtime', 'claude')
    assert run.returncode == 0, run.stdout + run.stderr
    state = read_attempt(project, run)
    committed = command(project, 'git', 'ls-files', check=True).stdout.split()
    assert {'Player.cs.meta', 'sound.wav'} <= set(committed)
    assert state['result']['criteriaVerdicts'][0]['verdict'] == 'pass'


def test_a_reverted_editor_edit_ships_the_green_writer_version_unflagged(project, claude_only, monkeypatch):
    (project / '.studio/implementation_loop.toml').write_text(
        '[gate]\ntest_command = "IFS= read -r line < hello.txt; [ \\"$line\\" = demo ]"\n'
        'require_mutation_check = false\n')
    command(project, 'git', 'commit', '-qam', 'gate reads hello.txt', check=True)
    monkeypatch.setenv('CLAUDE_FORGE_FIXTURE_MODE', 'breaks')
    run = cli(project, '--spec', '.studio/specs/demo.md', '--runtime', 'claude')
    assert run.returncode == 0, run.stdout + run.stderr
    state = read_attempt(project, run)
    editor = state['result']['editor']
    assert editor['reverted'] is True
    assert editor['tests']['passed'] is True
    assert editor['reverted_edit_tests']['passed'] is False
    assert state['result']['flagged'] is False
    assert (project / 'hello.txt').read_text() == 'demo'
    assert command(project, 'git', 'log', '-1', '--format=%s').stdout.strip() == 'writer: demo_unit'


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


def declare_game_pack(project, asset_command, static_checks='[]'):
    config = project / '.studio/implementation_loop.toml'
    config.write_text(f'[gate]\ntest_command="true"\nstatic_checks={static_checks}\n'
                      f'[packs.game.art]\nasset_command="{asset_command}"\nroutes=["code-built"]\n')
    command(project, 'git', 'commit', '-qam', 'declare the game pack', check=True)
    return config


def test_plan_carries_static_checks_unchanged_without_a_pack(project):
    config = project / '.studio/implementation_loop.toml'
    config.write_text('[gate]\ntest_command="true"\nstatic_checks=["make lint"]\n')
    command(project, 'git', 'commit', '-qam', 'lint', check=True)
    r = cli(project, 'Build a demo', '--plan')
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)['static_checks'] == ['make lint']


def test_plan_appends_one_quoted_pack_check_when_a_pack_is_declared(project):
    config = declare_game_pack(project, 'exit 0', '["make lint"]')
    r = cli(project, 'Build a demo', '--plan')
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)['static_checks'] == [
        'make lint',
        f'"{sys.executable}" "{STUDIO / "run_phase.py"}" check-packs --config "{config.resolve()}"',
    ]


def test_a_bad_packs_table_stops_the_plan_naming_the_config(project):
    config = project / '.studio/implementation_loop.toml'
    config.write_text('[gate]\ntest_command="true"\n[packs.game.art]\nroutes=["code-built"]\n')
    r = cli(project, 'Build a demo', '--plan')
    assert r.returncode != 0
    assert str(config.resolve()) in r.stderr and 'Shipped packs: game.' in r.stderr


def test_a_failing_pack_check_fails_the_writer_and_leaves_its_change_uncommitted(project, claude_only):
    declare_game_pack(project, 'exit 3')
    run = cli(project, '--spec', '.studio/specs/demo.md', '--runtime', 'claude')
    assert run.returncode != 0
    state = read_attempt(project, run)
    assert state['result']['writer']['static_ok'] is False
    assert state['result']['editorRan'] is False
    assert state['last_verified_sha'] == state['base_sha']
    assert command(project, 'git', 'log', '-1', '--format=%s').stdout.strip() == 'declare the game pack'
    assert command(project, 'git', 'status', '--porcelain', '--', 'hello.txt').stdout == '?? hello.txt\n'
    assert command(project, 'git', 'diff', '--cached', '--name-only').stdout == ''
    assert (project / 'hello.txt').read_text() == 'demo'
    git_dir = Path(command(project, 'git', 'rev-parse', '--absolute-git-dir').stdout.strip())
    saved = json.loads((git_dir / 'studio/pack-reports/game-art.json').read_text())
    assert saved['problems'] == ['asset command exited 3: exit 3']


def test_a_passing_pack_check_lets_the_writer_commit(project, claude_only):
    declare_game_pack(project, "echo '{\\\"assets\\\": []}'")
    run = cli(project, '--spec', '.studio/specs/demo.md', '--runtime', 'claude')
    assert run.returncode == 0, run.stdout + run.stderr
    state = read_attempt(project, run)
    assert state['result']['writer'].get('static_ok') is not False
    assert command(project, 'git', 'log', '-1', '--format=%s').stdout.strip() == 'writer: demo_unit'


WEB_RUNS = [{'suite': 'web', 'command': 'exit 7', 'exit_code': 7}, {'suite': None, 'command': 'true', 'exit_code': 0}]


def test_a_writer_change_under_a_red_web_suite_is_not_committed(project, claude_only, monkeypatch):
    declare_web_suite(project, 'exit 7')
    monkeypatch.setenv('CLAUDE_FORGE_FIXTURE_MODE', 'web')
    run = cli(project, '--spec', '.studio/specs/demo.md', '--runtime', 'claude')
    assert run.returncode != 0
    state = read_attempt(project, run)
    assert state['roles']['writer']['host_test'] == {
        'command': 'exit 7; true', 'passed': False, 'exit_code': 1, 'runs': WEB_RUNS}
    assert 'error' not in state
    assert state['result']['writer']['tests'] == {'command': 'exit 7; true', 'passed': False, 'exit_code': 1}
    assert state['last_verified_sha'] == state['base_sha']
    assert command(project, 'git', 'log', '-1', '--format=%s').stdout.strip() == 'declare the web suite'
    assert command(project, 'git', 'status', '--porcelain', '--', 'web', 'hello.txt').stdout == (
        ' M web/page.txt\n?? hello.txt\n')


def test_the_verdict_runs_the_copy_the_host_loaded_before_the_writer_changed_it(project, claude_only, monkeypatch):
    entry = install_source(project)
    declare_web_suite(project, 'exit 7')
    monkeypatch.setenv('CLAUDE_FORGE_FIXTURE_MODE', 'tamper')
    run = cli(project, '--spec', '.studio/specs/demo.md', '--runtime', 'claude', entry=entry)
    assert run.returncode != 0
    state = read_attempt(project, run)
    assert '"runs": []' in (project / '.studio/source/gate_routes.py').read_text()
    assert state['roles']['writer']['host_test']['runs'] == WEB_RUNS
    assert state['roles']['writer']['host_test']['passed'] is False
    assert state['last_verified_sha'] == state['base_sha']


def test_a_writer_change_to_the_gate_config_is_flagged_kept_and_fails_the_host(project, claude_only, monkeypatch):
    monkeypatch.setenv('CLAUDE_FORGE_FIXTURE_MODE', 'config')
    run = cli(project, '--spec', '.studio/specs/demo.md', '--runtime', 'claude')
    assert run.returncode == 1, run.stdout + run.stderr
    state = read_attempt(project, run)
    assert state['gate_config_changed'] is True
    assert 'error' not in state
    assert state['result']['delivered'] is True
    assert command(project, 'git', 'log', '-1', '--format=%s').stdout.strip() == 'writer: demo_unit'
    assert 'static_checks = []' in command(project, 'git', 'show', 'HEAD:.studio/implementation_loop.toml').stdout


def test_an_unchanged_gate_config_leaves_the_flag_down(project, claude_only):
    run = cli(project, '--spec', '.studio/specs/demo.md', '--runtime', 'claude')
    assert run.returncode == 0, run.stdout + run.stderr
    assert read_attempt(project, run)['gate_config_changed'] is False

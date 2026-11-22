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

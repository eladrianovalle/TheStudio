import json
from pathlib import Path
import subprocess
import sys

import pytest

from code_comments import added_comments, check_trees, marked_lines


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", tmp_path, *args], text=True).strip()

    git("init", "-b", "feature")
    git("config", "user.email", "test@example.org")
    git("config", "user.name", "Test")

    def commit(files):
        for path, text in files.items():
            (tmp_path / path).write_text(text)
        git("add", "-A")
        git("commit", "--allow-empty", "-qm", "forge fixture")
        return git("rev-parse", "HEAD")

    return tmp_path, commit


def test_new_comment_blocks_delivery(repo):
    root, commit = repo
    base = commit({"example.py": "url = 'https://example.org/#value'\n"})
    target = commit({"example.py": "url = 'https://example.org/#value'  # reason\n"})
    with pytest.raises(ValueError, match="example.py:1: agent-added"):
        check_trees(root, base, target)


@pytest.mark.parametrize(("language", "source", "lines"), [
    ("python", "def f():\n    \"\"\"docs\n    here\"\"\"\n    return '# ok'\n", [2, 3]),
    ("python", "#!/usr/bin/env python3\ns = '''# string'''\n", []),
    ("javascript", "const url = `http://host/${1 /* note */}`;", [1]),
    ("javascript", "const pattern = /[/*]/; const url = 'http://x';", []),
    ("csharp", '#if DEBUG // note\n#endif\nclass C { string s = @"//"; }', [1]),
    ("cpp", '#define URL "//"\n#define COUNT 42 // note', [2]),
    ("gitignore", "\\#literal\n# note", [2]),
    ("rust", '/// docs\nfn f() { let _ = r#"//"#; /* why */ }', [1, 2]),
    ("bash", "#!/bin/sh\ncat <<'EOF'\n# data\nEOF\necho x#y # comment", [5]),
    ("yaml", "body: |\n  # data\nkey: '#' # comment", [3]),
    ("toml", "s = \"\"\"\n# data\n\"\"\" # note\nliteral = '#'\n", [3]),
    ("json", '{"value": "// ok", /* note */ "b": 1}', [1]),
    ("html", "<script>const x = '//'; // hi\n</script><!-- note -->", [1, 2]),
])
def test_comment_nodes_and_literal_data(language, source, lines):
    assert list(added_comments([], marked_lines(source.encode(), language))) == lines


def test_existing_comments_survive_code_edits_and_rename(repo):
    root, commit = repo
    base = commit({"app.py": "# old\nx = 3  # units\ny = 4\nz = 5\n"})
    (root / "app.py").rename(root / "renamed.py")
    target = commit({"renamed.py": "# old\nx = 6  # units\ny = 4\nz = 5\n", "notes.md": "# Docs\n"})
    check_trees(root, base, target)


def test_extend_existing_multiline_comment(repo):
    root, commit = repo
    base = commit({"app.js": "/* old\nline */\nconst a = 1;\n"})
    target = commit({"app.js": "/* old\nextra\nline */\nconst a = 1;\n"})
    with pytest.raises(ValueError, match="app.js:2:"):
        check_trees(root, base, target)


def test_unsupported_source_fails_closed(repo):
    root, commit = repo
    base = commit({})
    target = commit({"app.unknownlang": "code"})
    with pytest.raises(ValueError, match="app.unknownlang: no comment checker"):
        check_trees(root, base, target)


def test_missing_parser_blocks_source(monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(ValueError, match="Install @ast-grep"):
        marked_lines(b"let x = 1", "javascript")


@pytest.mark.parametrize("comment_role", ["writer", "editor", None])
def test_native_finalizer_verifies_each_commit_before_delivery(repo, comment_role):
    root, commit = repo
    base = commit({})
    commit({"app.py": "a = 1" + (" # old" if comment_role == "writer" else "")})
    head = commit({"app.py": "a = 2" + (" # new" if comment_role == "editor" else "")})
    candidate = {"writer": {"unit_id": "demo"}, "pendingCommentCheck": True, "delivered": False}
    checker = Path(__file__).resolve().parents[1] / "code_comments.py"
    result = subprocess.run(
        [sys.executable, checker, "--repo", root, "--base", base, "--finalize-branch", "feature"],
        input=json.dumps(candidate), capture_output=True, text=True,
    )
    if comment_role:
        assert result.returncode and "app.py:1" in result.stderr and not result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {
            **candidate, "delivered": True, "pendingCommentCheck": False, "verified_sha": head,
        }

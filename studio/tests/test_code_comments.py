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


UNITY_ASSETS = {
    "Player.cs": b"class Player {}\n",
    "Player.cs.meta": b"fileFormatVersion: 2\nguid: 0123456789abcdef0123456789abcdef\n",
    "Player.prefab": b"%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!1001 &100 stripped\nPrefabInstance:\n",
    "sound.wav": b"RIFF$\0\0\0WAVEfmt \x10\0\0\0\x01\0\x01\0D\xac\0\0\x88X\x01\0\x02\0\x10\0data\0\0\0\0",
}


def test_unity_serialization_and_binary_assets_pass_the_delivery_gate(repo):
    root, commit = repo
    base = commit({})
    for path, data in UNITY_ASSETS.items():
        (root / path).write_bytes(data)
    head = commit({})
    candidate = {"writer": {"unit_id": "demo"}, "pendingCommentCheck": True, "delivered": False}
    checker = Path(__file__).resolve().parents[1] / "code_comments.py"
    result = subprocess.run(
        [sys.executable, checker, "--repo", root, "--base", base, "--finalize-branch", "feature"],
        input=json.dumps(candidate), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["verified_sha"] == head


def test_unsupported_text_source_still_fails_beside_assets(repo):
    root, commit = repo
    base = commit({})
    for path, data in UNITY_ASSETS.items():
        (root / path).write_bytes(data)
    target = commit({"Shader.unknownlang": "// note\n"})
    with pytest.raises(ValueError, match="Shader.unknownlang: no comment checker"):
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


@pytest.mark.parametrize(("html", "expected_lines"), [
    ('<script type="text/template"><div class="title">Hello</div></script>', []),
    ('<script type="text/template"><b onclick="f() /* text */">hello</b></script>', []),
    ('<script type="application/ld+json">{"message": "/* data */"}</script>', []),
    ('<script type="module">export const x = 1; // comment</script>', [1]),
    ('<SCRIPT TYPE=TEXT/JAVASCRIPT>/* comment */</SCRIPT>', [1]),
    ('<script type="importmap">{"imports": {"lib": "/lib.js"}}</script>', []),
    ('<button onclick="alert(1) /* new explanation */">Go</button>', [1]),
    ('<div style="color: red; /* new explanation */">Go</div>', [1]),
    ('<button ONCLICK =\n "return &quot;/* text */&quot;;\n // comment">Go</button>', [3]),
    ('<button onclick="f()&#10;&#47;* comment *&#47;">Go</button>', [1]),
    ('<div style="--label: &quot;/* text */&quot;;">Go</div>', []),
    ('<div data-onclick="/* data */" title="// data" only="some / text">Go</div>', []),
    ('<button onclick="return false" style=color:red>Go</button>', []),
    ('<input onfocus="return false; // comment" />', [1]),
    ('<style>span { color: red; /* explanation */ }</style>', [1]),
    ('<script type="text/javascript; charset=utf-8">// data</script>', []),
    ('<script type="text/plain">// data</script>\n<script>// comment</script>', [2]),
])
def test_forge_html_comments_in_git_changes(repo, html, expected_lines):
    root, commit = repo
    base = commit({})
    target = commit({"index.html": html})
    if expected_lines:
        with pytest.raises(ValueError) as failure:
            check_trees(root, base, target)
        assert str(failure.value).splitlines() == [
            f"index.html:{line}: agent-added code comment" for line in expected_lines
        ]
    else:
        check_trees(root, base, target)

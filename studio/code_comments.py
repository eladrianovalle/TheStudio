import argparse
import ast
from collections import Counter, deque
from difflib import SequenceMatcher
from html import unescape
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tokenize

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


LANGUAGES = {
    "python": "py pyi pyw", "javascript": "js mjs cjs", "typescript": "ts mts cts",
    "jsx": "jsx", "tsx": "tsx", "c": "c h", "cpp": "cpp cc cxx hpp hxx",
    "csharp": "cs", "rust": "rs", "go": "go", "java": "java", "kotlin": "kt kts",
    "bash": "sh bash", "ruby": "rb", "lua": "lua", "css": "css",
    "html": "html htm", "yaml": "yaml yml", "toml": "toml", "json": "json jsonc asmdef asmref",
}
BY_EXTENSION = {ext: name for name, exts in LANGUAGES.items() for ext in exts.split()}
BY_NAME = {"Gemfile": "ruby", ".gitignore": "gitignore"}
DOCUMENTS = {".md", ".markdown", ".rst", ".txt", ".csv", ".tsv"}
ASSETS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".pdf"}
INTERPRETER = re.compile(r"^#!\s*(?:/\S*/env\s+(?:-S\s+)?|/\S*/)([\w.+-]+)(?:\s|$)")
RUNNERS = {"sh": "bash", "bash": "bash", "node": "javascript", "ruby": "ruby"}


JS_TYPES = set("""
    application/ecmascript application/javascript application/x-ecmascript application/x-javascript
    text/ecmascript text/javascript text/javascript1.0 text/javascript1.1 text/javascript1.2
    text/javascript1.3 text/javascript1.4 text/javascript1.5 text/jscript text/livescript
    text/x-ecmascript text/x-javascript
""".split())

HTML_EVENTS = set("""
    abort afterprint animationcancel animationend animationiteration animationstart auxclick
    beforeinput beforeinstallprompt beforematch beforeprint beforetoggle beforeunload beforexrselect blur cancel
    canplay canplaythrough change click close command contextlost contextmenu contextrestored
    contentvisibilityautostatechange copy cuechange cut dblclick deviceorientation deviceorientationabsolute devicemotion
    drag dragend dragenter dragleave dragover dragstart drop durationchange emptied encrypted ended enterpictureinpicture error
    focus focusin focusout formdata fullscreenchange fullscreenerror gamepadconnected
    gamepaddisconnected gotpointercapture hashchange input invalid keydown keypress keyup
    languagechange leavepictureinpicture load loadeddata loadedmetadata loadstart lostpointercapture message messageerror
    mousedown mouseenter mouseleave mousemove mouseout mouseover mouseup mousewheel offline online
    pagehide pagereveal pageshow pageswap paste pause play playing pointercancel pointerdown
    pointerenter pointerleave pointerlockchange pointerlockerror pointermove pointerout pointerover pointerrawupdate pointerup popstate
    progress ratechange readystatechange rejectionhandled reset resize scroll scrollend
    scrollsnapchange scrollsnapchanging securitypolicyviolation seeked seeking select selectionchange
    selectstart slotchange stalled storage submit suspend timeupdate toggle touchcancel touchend
    touchmove touchstart transitioncancel transitionend transitionrun transitionstart
    unhandledrejection unload visibilitychange volumechange waiting waitingforkey webkitanimationend
    webkitanimationiteration webkitanimationstart webkittransitionend wheel
""".split())


def git(repo, *args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", repo, *args])


def language(path, data):
    suffix = Path(path).suffix.lower()
    first = data.partition(b"\n")[0].decode("ascii", errors="replace")
    runner = INTERPRETER.match(first)
    if runner:
        name = runner[1]
        if re.fullmatch(r"python(?:[23](?:\.\d+)?)?", name):
            return "python"
        if name in RUNNERS:
            return RUNNERS[name]
        raise ValueError(f"{path}: unsupported interpreter {name}")
    if suffix in DOCUMENTS or suffix in ASSETS:
        return None
    name = BY_NAME.get(Path(path).name) or BY_EXTENSION.get(suffix[1:])
    if not name:
        raise ValueError(f"{path}: no comment checker for this file type")
    return name


def python_comments(source):
    for token in tokenize.generate_tokens(StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            yield token.start[0], token.string
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                yield node.lineno, ast.get_source_segment(source, node)


def syntax_nodes(source, name, kinds):
    try:
        result = subprocess.run(
            ["ast-grep", "run", "--lang", name, "--kind", kinds, "--stdin", "--json=compact"],
            input=source, text=True, encoding="utf-8", capture_output=True,
        )
    except FileNotFoundError as exc:
        raise ValueError("Install @ast-grep/cli@0.51.3 to check this language") from exc
    if result.returncode not in (0, 1) or result.stderr:
        raise ValueError(result.stderr.strip() or "ast-grep failed")
    return json.loads(result.stdout)


def html_body_language(tag, attributes):
    kind = attributes.get("type", "")
    if tag == "style":
        return "css" if kind.lower() in {"", "text/css"} else None
    if tag != "script" or "src" in attributes:
        return None
    if "type" not in attributes and attributes.get("language"):
        kind = "text/" + attributes["language"]
    if kind.lower() in {"importmap", "speculationrules"}:
        return "json"
    if kind == "" or kind.lower() == "module" or kind.strip(" \t\n\f\r").lower() in JS_TYPES:
        return "javascript"
    return None


def html_attribute_comments(raw, first_line, name):
    lang, prefix = ("css", "a{") if name == "style" else ("javascript", "function handler(event){")
    decoded = []
    line_numbers = []
    for number, line in enumerate(raw.split("\n"), first_line):
        value = unescape(line)
        decoded.append(value)
        line_numbers.extend([number] * (value.count("\n") + 1))
    fragment = prefix + "\n".join(decoded) + "\n}"
    for start, comment in tree_comments(fragment, lang):
        for index, part in enumerate(comment.split("\n"), start - 1):
            if part:
                yield line_numbers[index], part


def html_comments(source):
    bodies = {node["range"]["byteOffset"]["start"]: node for node in syntax_nodes(source, "html", "raw_text")}
    attributes = deque(syntax_nodes(source, "html", "attribute"))
    for tag in syntax_nodes(source, "html", "start_tag,self_closing_tag"):
        end = tag["range"]["byteOffset"]["end"]
        values = {}
        while attributes and attributes[0]["range"]["byteOffset"]["start"] < end:
            attr = attributes.popleft()
            raw = attr["text"]
            key, _, tail = raw.partition("=")
            name = key.strip().lower()
            if name in values:
                continue
            value = tail.lstrip()
            first_line = attr["range"]["start"]["line"] + 1 + raw[:len(raw) - len(value)].count("\n")
            if value.startswith(('"', "'")):
                value = value[1:-1]
            values[name] = unescape(value)
            if name == "style" or (name.startswith("on") and name[2:] in HTML_EVENTS):
                yield from html_attribute_comments(value, first_line, name)
        body = bodies.get(end)
        if body:
            name = re.match(r"<([^\s/>]+)", tag["text"])[1].lower()
            lang = html_body_language(name, values)
            if lang:
                for line, comment in tree_comments(body["text"], lang):
                    yield body["range"]["start"]["line"] + line, comment


def tree_comments(source, name):
    errors = syntax_nodes(source, name, "ERROR")
    if errors:
        raise ValueError(f"unparsed {name} syntax at line {errors[0]['range']['start']['line'] + 1}")
    kinds = {
        "java": "line_comment,block_comment", "rust": "line_comment,block_comment",
        "kotlin": "line_comment,multiline_comment",
    }.get(name, "comment")
    for node in syntax_nodes(source, name, kinds):
        yield node["range"]["start"]["line"] + 1, node["text"]
    if name in {"c", "cpp"}:
        for argument in syntax_nodes(source, name, "preproc_arg"):
            for node in syntax_nodes(argument["text"], name, "comment"):
                yield argument["range"]["start"]["line"] + node["range"]["start"]["line"] + 1, node["text"]
    if name == "html":
        yield from html_comments(source)


def toml_comments(source):
    tomllib.loads(source)
    delimiter = ""
    for number, line in enumerate(source.split("\n"), 1):
        i = 0
        while i < len(line):
            char = line[i]
            if delimiter:
                if char == "\\" and delimiter.startswith('"'):
                    i += 2
                    continue
                if line.startswith(delimiter, i):
                    i += len(delimiter)
                    if len(delimiter) == 3:
                        while i < len(line) and line[i] == char:
                            i += 1
                    delimiter = ""
                    continue
            elif char == "#":
                yield number, line[i:]
                break
            elif char in {"'", '"'}:
                delimiter = char * 3 if line.startswith(char * 3, i) else char
                i += len(delimiter)
                continue
            i += 1


def marked_lines(data, name):
    encoding = tokenize.detect_encoding(BytesIO(data).readline)[0] if name == "python" else "utf-8-sig"
    source = data.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    marks = [[] for _ in lines]
    if name == "python":
        comments = python_comments(source)
    elif name == "gitignore":
        comments = ((i, line) for i, line in enumerate(lines, 1) if line.startswith("#"))
    elif name == "toml":
        comments = toml_comments(source)
    else:
        comments = tree_comments(source, name)
    for number, comment in comments:
        if number == 1 and INTERPRETER.match(comment) and source.startswith(comment):
            continue
        for delta, part in enumerate(comment.split("\n")):
            if part:
                marks[number - 1 + delta].append(part)
    return [(line, tuple(parts)) for line, parts in zip(lines, marks)]


def added_comments(old, new):
    for op, left, right, start, end in SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        remaining = Counter(part for _, parts in old[left:right] for part in parts)
        for i in range(start, end):
            for part in new[i][1]:
                if remaining[part] == 0:
                    yield i + 1
                    break
                remaining[part] -= 1


def check_trees(repo, base, target):
    fields = iter(git(repo, "diff-tree", "--raw", "-r", "-z", "--no-commit-id", "--no-abbrev",
                      "-M", base, target, "--").split(b"\0"))
    findings = []
    for header in fields:
        if not header:
            break
        before, after, old_id, new_id, status = header[1:].decode().split()
        old_path = os.fsdecode(next(fields))
        path = os.fsdecode(next(fields)) if status.startswith("R") else old_path
        if after in {"000000", "120000"}:
            continue
        if not after.startswith("100"):
            raise ValueError(f"{path}: cannot verify changed Git entry of mode {after}")
        new_data = git(repo, "cat-file", "blob", new_id)
        name = language(path, new_data)
        if name is None:
            continue
        try:
            old = []
            if before.startswith("100"):
                old_data = git(repo, "cat-file", "blob", old_id)
                if old_path == path or language(old_path, old_data) == name:
                    old = marked_lines(old_data, name)
            new = marked_lines(new_data, name)
            findings.extend(f"{path}:{line}: agent-added code comment" for line in added_comments(old, new))
        except (ValueError, SyntaxError, tokenize.TokenError, subprocess.CalledProcessError) as exc:
            raise ValueError(f"{path}: comment check failed: {exc}") from exc
    if findings:
        raise ValueError("\n".join(findings))


def finalize(repo, base, branch, candidate):
    if candidate.get("delivered") is not False or candidate.get("pendingCommentCheck") is not True:
        raise ValueError("Expected a pending Forge result")
    if git(repo, "branch", "--show-current").decode().strip() != branch:
        raise ValueError("Forge branch changed")
    base = git(repo, "rev-parse", "--verify", "--end-of-options", base + "^{commit}").decode().strip()
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    git(repo, "merge-base", "--is-ancestor", base, head)
    previous = base
    for row in git(repo, "rev-list", "--reverse", "--parents", f"{base}..{head}").decode().splitlines():
        commit, *parents = row.split()
        if parents != [previous]:
            raise ValueError("Cannot attribute a merged history to this Forge run")
        check_trees(repo, previous, commit)
        previous = commit
    if head == base:
        raise ValueError("No Forge commit to verify")
    if git(repo, "diff", "--name-only", head, "--") or git(repo, "diff", "--cached", "--name-only", head, "--"):
        raise ValueError("Uncommitted changes outside the verified commits")
    unit = candidate["writer"]["unit_id"]
    allowed = {f"reviewer-concerns/{unit}.md"}
    for role in ("writer", "editor"):
        allowed.add(f".studio/output/impl_loop/{unit}/impl--{unit}--{role}.json")
    untracked = git(repo, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    if any(os.fsdecode(path) not in allowed for path in untracked if path):
        raise ValueError("Untracked files outside the Forge records")
    if git(repo, "rev-parse", "HEAD").decode().strip() != head:
        raise ValueError("Forge HEAD changed during verification")
    return {**candidate, "delivered": True, "pendingCommentCheck": False, "verified_sha": head}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--tree")
    mode.add_argument("--finalize-branch")
    args = parser.parse_args()
    if args.tree:
        check_trees(args.repo, args.base, args.tree)
    else:
        print(json.dumps(finalize(args.repo, args.base, args.finalize_branch, json.load(sys.stdin))))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        sys.exit(f"Forge comment check blocked delivery: {error}")

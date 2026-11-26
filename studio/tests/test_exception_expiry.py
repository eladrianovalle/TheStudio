import re
import subprocess
from datetime import date, timedelta
from pathlib import Path

from code_comments import DOCUMENTS

REPO_ROOT = Path(__file__).resolve().parents[2]

EXCEPTION_DATE = re.compile(r"\buntil=(\d{4}-\d{2}-\d{2})(?!\d)(.*)$")

FIX_AND_SEE = (
    "  Fix: remove the exception and fix the line, or have a person set a new date and reason\n"
    "  See .claude/commands/correct.md"
)


def expired_exceptions(files: list[tuple[str, str]], today: date) -> list[str]:
    reports: list[str] = []
    for path, text in files:
        if Path(path).suffix.lower() in DOCUMENTS:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            match = EXCEPTION_DATE.search(line)
            if not match:
                continue
            written_date, rest_of_line = match.groups()
            try:
                expiry = date.fromisoformat(written_date)
            except ValueError:
                problem = f"exception date {written_date} is not a real date"
            else:
                if expiry < today:
                    problem = f"exception expired on {written_date}"
                elif not re.match(r"\s+\w", rest_of_line):
                    problem = f"exception until {written_date} gives no reason"
                else:
                    continue
            reports.append(f"{path}:{line_number}: {problem}\n{FIX_AND_SEE}")
    return reports


def _tracked_files(root: Path) -> list[tuple[str, str]]:
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split("\0")
    files: list[tuple[str, str]] = []
    for relative_path in listed:
        path = root / relative_path
        if relative_path and path.is_file():
            files.append((relative_path, path.read_text(encoding="utf-8", errors="replace")))
    return files


def _real_line_with_a_marker() -> tuple[str, int, str]:
    relative_path = "studio/tests/test_command_descriptions.py"
    lines = (REPO_ROOT / relative_path).read_text(encoding="utf-8").splitlines()
    line_index = lines.index("from install import SLASH_COMMANDS  # noqa: E402")
    return relative_path, line_index + 1, lines[line_index]


def test_no_tracked_exception_has_expired():
    reports = expired_exceptions(_tracked_files(REPO_ROOT), date.today())
    assert reports == [], "\n".join(reports)


def test_a_planted_exception_past_its_date_fails_with_fix_and_see():
    relative_path, line_number, real_line = _real_line_with_a_marker()
    today = date.today()
    yesterday = today - timedelta(days=1)
    planted = f"{real_line} until={yesterday.isoformat()} waits on the conftest move"
    text = "\n".join(["import sys"] * (line_number - 1) + [planted])

    reports = expired_exceptions([(relative_path, text)], today)

    assert reports == [
        f"{relative_path}:{line_number}: exception expired on {yesterday.isoformat()}\n"
        "  Fix: remove the exception and fix the line, or have a person set a new date and reason\n"
        "  See .claude/commands/correct.md"
    ]


def test_a_date_of_today_or_later_passes():
    today = date.today()
    tomorrow = today + timedelta(days=1)
    files = [
        ("a.py", f"x = 1  # noqa: E731 until={today.isoformat()} waits on the move"),
        ("b.py", f"y = 2  # noqa: E731 until={tomorrow.isoformat()} waits on the move"),
    ]
    assert expired_exceptions(files, today) == []


def test_a_date_that_is_not_real_fails():
    today = date.today()
    impossible = f"{today.year + 1}-02-30"
    reports = expired_exceptions([("a.py", f"x = 1  # noqa: E731 until={impossible} reason")], today)
    assert reports == [f"a.py:1: exception date {impossible} is not a real date\n{FIX_AND_SEE}"]


def test_a_date_with_no_reason_fails():
    today = date.today()
    later = (today + timedelta(days=30)).isoformat()
    reports = expired_exceptions([("a.py", f"x = 1  # noqa: E731 until={later}")], today)
    assert reports == [f"a.py:1: exception until {later} gives no reason\n{FIX_AND_SEE}"]


def test_only_the_line_holding_the_exception_is_named():
    today = date.today()
    past = (today - timedelta(days=3)).isoformat()
    text = f"a = 1\nb = 2\nc = 3  # noqa: E731 until={past} reason\n"
    reports = expired_exceptions([("pkg/mod.py", text)], today)
    assert [report.splitlines()[0] for report in reports] == [
        f"pkg/mod.py:3: exception expired on {past}"
    ]


def test_an_exception_in_a_document_is_ignored():
    today = date.today()
    past = (today - timedelta(days=3)).isoformat()
    files = [
        ("docs/guide.md", f"Write `# noqa: E402 until={past} reason` on the line."),
        ("NOTES.TXT", f"until={past}"),
    ]
    assert expired_exceptions(files, today) == []


def test_a_longer_name_ending_in_until_is_not_an_exception():
    today = date.today()
    past = (today - timedelta(days=3)).isoformat()
    assert expired_exceptions([("a.py", f'wait_until="{past}"')], today) == []
    assert expired_exceptions([("a.py", f'wait_until={past}')], today) == []

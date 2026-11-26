import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"
CREATE_COMMAND = COMMANDS_DIR / "create-verification-skill.md"
MAINTAIN_COMMAND = COMMANDS_DIR / "maintain-verification-skill.md"
USAGE_DOC = REPO_ROOT / "studio" / "docs" / "CLAUDE_CODE_USAGE.md"

MIT_PERMISSION_SENTENCE = (
    "Permission is hereby granted, free of charge, to any person obtaining a copy "
    "of this software and associated documentation files (the \"Software\"), to deal "
    "in the Software without restriction, including without limitation the rights "
    "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell "
    "copies of the Software, and to permit persons to whom the Software is "
    "furnished to do so, subject to the following conditions:"
)

PSTACK_MIT_NOTICE = (
    "MIT License\n\n"
    "Copyright (c) 2026 Lauren Tan\n\n"
    + MIT_PERMISSION_SENTENCE
    + "\n\nThe above copyright notice and this permission notice shall be included in all "
    "copies or substantial portions of the Software.\n\n"
    "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR "
    "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, "
    "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE "
    "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER "
    "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, "
    "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE "
    "SOFTWARE."
)

HAND_OFF_TEMPLATE = """\
Verify skill: .claude/skills/verify-<app>/  (uncommitted, N files)
Proved: yes | NO: <step that failed> — <error line>
Feature driven: features/<file>.md via <entry point>
Evidence after cleanup: <absolute path>  <bytes>   (one line per file, from ls -l)
Stand-in gaps: none | <setup steps the proof's stand-in did that the real target will not>
Map: <n> features (<names>); not yet driven: <names>
Wired: CLAUDE.md line <n> | not wired: <why>
Next: review and land as one PR; keep it honest with /maintain-verification-skill (schedule: CLAUDE_CODE_USAGE.md)."""

CURSOR_ONLY_NAMES = {
    "a .cursor/ path": re.compile(r"\.cursor/"),
    "the AskQuestion tool": re.compile(r"AskQuestion"),
    "a .mdc rule file": re.compile(r"\.mdc\b"),
    "Task as a tool name": re.compile(r"`Task`|\bTask tool\b|\bTask\(|\"Task\""),
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def frontmatter_of(text: str) -> str:
    if not text.startswith("---\n"):
        return ""
    closing = text.find("\n---\n", 4)
    if closing == -1:
        return ""
    return text[4:closing]


def body_of(text: str) -> str:
    closing = text.find("\n---\n", 4)
    return text[closing + 5:] if text.startswith("---\n") and closing != -1 else text


def verification_command_files() -> list[Path]:
    return sorted(COMMANDS_DIR.glob("*-verification-skill.md"))


class TestEveryVerificationCommandIsFound(unittest.TestCase):
    def test_both_commands_are_among_the_files_checked(self):
        for command in (CREATE_COMMAND, MAINTAIN_COMMAND):
            with self.subTest(command=command.name):
                self.assertIn(
                    command,
                    verification_command_files(),
                    "The licence and Cursor-name checks below iterate every "
                    "*-verification-skill.md command. A command they do not find goes unchecked.",
                )


class TestTheMitNoticeTravelsWithTheFile(unittest.TestCase):
    def test_every_verification_command_ends_with_attribution_and_the_full_notice(self):
        for path in verification_command_files():
            text = collapse_whitespace(read_text(path))
            skill_name = path.stem
            with self.subTest(command=path.name):
                self.assertTrue(
                    text.endswith(collapse_whitespace(PSTACK_MIT_NOTICE)),
                    f"{path.name} adapts pstack, whose MIT licence requires its copyright and "
                    f"permission notice in every copy. The command file is what installs into "
                    f"each consuming repo, so it must end with that notice, word for word.",
                )
                notice_start = text.rfind("MIT License")
                attribution = text[:notice_start].rstrip()[-400:]
                self.assertIn(f"Adapted from `{skill_name}` in pstack by Lauren Tan", attribution)
                self.assertIn(
                    f"harness/pstack/claude-code/skills/{skill_name}/", attribution
                )
                self.assertIn("cursor/plugins", attribution)


class TestVerificationCommandsOnlyRunWhenAPersonAsks(unittest.TestCase):
    def test_every_verification_command_disables_model_invocation(self):
        for path in verification_command_files():
            with self.subTest(command=path.name):
                frontmatter_lines = frontmatter_of(read_text(path)).splitlines()
                self.assertIn(
                    "disable-model-invocation: true",
                    [line.strip() for line in frontmatter_lines],
                    f"{path.name} must set disable-model-invocation: true in its frontmatter, "
                    f"as pstack's skills do, so an agent cannot start it on its own.",
                )


class TestNoCursorOnlyNamesSurvive(unittest.TestCase):
    def test_no_verification_command_names_a_cursor_only_thing(self):
        for path in verification_command_files():
            text = read_text(path)
            for description, pattern in CURSOR_ONLY_NAMES.items():
                with self.subTest(command=path.name, name=description):
                    match = pattern.search(text)
                    self.assertIsNone(
                        match,
                        f"{path.name} contains {description} ({match.group(0) if match else ''!r}). "
                        f"Claude Code has none of these; map it the way pstack's Claude Code "
                        f"adapter does.",
                    )


class TestTheCreateCommandKeepsPstacksSteps(unittest.TestCase):
    def setUp(self):
        self.body = body_of(read_text(CREATE_COMMAND))

    def test_it_asks_the_five_interview_questions(self):
        for question in ("Surface", "Run", "Drive", "Observe", "Isolate"):
            with self.subTest(question=question):
                self.assertIn(f"- **{question}:**", self.body)

    def test_it_fixes_a_broken_base_before_generating(self):
        self.assertIn("fix that first (or report it precisely)", self.body)
        self.assertIn("verification scaffolding", self.body)

    def test_the_generated_skill_has_each_section_with_its_rule(self):
        rules = {
            "Launch": "Ready means usable, not just that a process answers.",
            "Doctor": "is this instance worth driving?",
            "Drive": "Prefer stable handles",
            "Evidence": "exercise the real user path, not internal setters or test-only endpoints",
            "Cleanup": "Never kill by process name; kill what you started.",
            "Helpers": "A helper the reader has to reverse-engineer is not a helper.",
        }
        for section, rule in rules.items():
            with self.subTest(section=section):
                self.assertIn(f"- **{section}:**", self.body)
                self.assertIn(rule, self.body)

    def test_feature_files_use_the_four_headings_verbatim(self):
        for heading in (
            "## Sub-features",
            "## How to get to it (user POV)",
            "## Driving it with <harness>",
            "## Gotchas",
        ):
            with self.subTest(heading=heading):
                self.assertIn(f"`{heading}`", self.body)
        self.assertIn("Never weaken the journey to make it pass.", self.body)

    def test_it_proves_once_and_confirms_the_evidence_survived_cleanup(self):
        self.assertIn("drive ONE mapped feature", self.body)
        self.assertIn("confirm the evidence still exists", self.body)
        self.assertIn("A generated skill that was never executed is a draft, not a deliverable.", self.body)

    def test_it_writes_the_skill_under_claude_skills(self):
        self.assertIn(".claude/skills/verify-<app>/SKILL.md", self.body)
        self.assertIn(".claude/skills/verify-<app>/features/README.md", self.body)


class TestTheCreateCommandCarriesTheStudioSteps(unittest.TestCase):
    def setUp(self):
        self.body = body_of(read_text(CREATE_COMMAND))

    def test_it_refuses_when_a_verify_skill_already_exists(self):
        locate = self.body[: self.body.index("## 1.")]
        self.assertIn(".claude/skills/verify-*/", locate)
        self.assertIn("/maintain-verification-skill", locate)
        self.assertIn("stop", locate.lower())

    def test_it_seeds_read_only_from_smoke_and_the_observe_command(self):
        self.assertIn(".studio/smoke.toml", self.body)
        self.assertIn("[gate] observe_command", self.body)
        self.assertIn("--help", self.body)
        self.assertIn("read only", self.body)

    def test_evidence_goes_outside_the_checkout_as_absolute_paths(self):
        self.assertIn("outside the checkout", self.body)
        self.assertIn("absolute path", self.body)

    def test_the_proof_runs_in_a_fresh_worktree(self):
        self.assertIn("git worktree add --detach", self.body)
        self.assertIn("git worktree remove", self.body)
        self.assertIn("ls -l", self.body)

    def test_it_writes_one_pointer_line_outside_the_studio_sentinels(self):
        self.assertIn("STUDIO:CODING_PRINCIPLES", self.body)
        pointer = re.search(r"^ *(- Before verifying anything .*)$", self.body, re.MULTILINE)
        self.assertIsNotNone(pointer, "the command must give the exact CLAUDE.md pointer line")
        self.assertIn(".claude/skills/verify-<app>/SKILL.md", pointer.group(1))
        self.assertIn(".claude/skills/verify-<app>/features/README.md", pointer.group(1))

    def test_it_does_not_commit(self):
        self.assertIn("Do not commit", self.body)

    def test_it_carries_the_hand_off_reply_template_word_for_word(self):
        self.assertIn(HAND_OFF_TEMPLATE, self.body)


class TestTheDocsSayWhenToUseIt(unittest.TestCase):
    def test_readme_has_a_row(self):
        readme = read_text(REPO_ROOT / "README.md")
        self.assertRegex(readme, r"(?m)^\| `/create-verification-skill` \| .{40,}\|$")

    def test_the_utility_slash_commands_table_has_a_row(self):
        usage = read_text(REPO_ROOT / "studio" / "docs" / "CLAUDE_CODE_USAGE.md")
        table = usage.split("## Utility Slash Commands", 1)[1].split("\n## ", 1)[0]
        self.assertRegex(table, r"(?m)^\| `/create-verification-skill` \| .{40,}\|$")


PSTACK_OUTCOMES = (
    "- **clean** — every feature got source and live coverage; nothing worth shipping. "
    "No branch, no PR.",
    "- **changed** — one PR ships proven doc, harness, or map corrections.",
    "- **blocked** — coverage could not finish or a proven fix could not ship safely. "
    "Say exactly what blocked it.",
)

PSTACK_EDIT_SCOPE = (
    "Only edit the verification skill's own directory (its SKILL.md, features/, and any "
    "harness scripts it owns). Never edit product code during a run: a behavior the map "
    "describes that the app no longer does is either doc drift (fix the map) or a product "
    "regression (report it, don't paper over it in docs)."
)

PSTACK_STEP_TITLES = (
    "0. **Locate the target.**",
    "1. **Index hygiene.**",
    "2. **Source wave.**",
    "3. **Reconcile.**",
    "4. **Live pass.**",
    "5. **Triage.**",
    "6. **Ship or stop.**",
)

OUTCOME_LINE = "OUTCOME: clean|changed|blocked — <one line>"


def maintain_step(body: str, number: int) -> str:
    start = body.index(PSTACK_STEP_TITLES[number])
    if number + 1 < len(PSTACK_STEP_TITLES):
        return body[start: body.index(PSTACK_STEP_TITLES[number + 1])]
    end = body.find(" ## ", start)
    return body[start:] if end == -1 else body[start:end]


class TestTheMaintainCommandKeepsPstacksPass(unittest.TestCase):
    def setUp(self):
        self.body = collapse_whitespace(body_of(read_text(MAINTAIN_COMMAND)))

    def test_it_keeps_the_three_outcomes_word_for_word(self):
        for outcome in PSTACK_OUTCOMES:
            with self.subTest(outcome=outcome.split("**")[1]):
                self.assertIn(outcome, self.body)

    def test_it_keeps_the_edit_scope_word_for_word(self):
        self.assertIn(PSTACK_EDIT_SCOPE, self.body)

    def test_it_keeps_steps_zero_to_six_in_order(self):
        positions = [self.body.find(title) for title in PSTACK_STEP_TITLES]
        self.assertNotIn(-1, positions, "every pstack step must keep its number and title")
        self.assertEqual(positions, sorted(positions))

    def test_the_live_pass_runs_even_when_source_looks_clean(self):
        live_pass = maintain_step(self.body, 4)
        self.assertIn("Required even when source looks clean.", live_pass)
        self.assertIn("the skill's Launch section decides, not this one", live_pass)

    def test_the_live_pass_holds_the_three_invariants(self):
        live_pass = maintain_step(self.body, 4)
        for invariant in (
            "(1) never drive an instance you haven't health-checked since it last did "
            "something surprising",
            "(2) evidence captured so far survives every cleanup, checked at its named "
            "location, not assumed",
            "(3) nothing a drive started outlives that drive's usefulness",
        ):
            with self.subTest(invariant=invariant[:3]):
                self.assertIn(invariant, live_pass)

    def test_unreachable_needs_a_named_prerequisite(self):
        live_pass = maintain_step(self.body, 4)
        self.assertIn(
            "A feature that can't be reached is `verified-unreachable` only with the concrete "
            "prerequisite (auth, entitlement, OS, external state) and the route attempted",
            live_pass,
        )
        self.assertIn("Any harness fix from triage gets re-driven live before it ships.", live_pass)
        self.assertIn("Final teardown happens after the last drive of the run", live_pass)

    def test_reconcile_and_triage_keep_their_rules(self):
        self.assertIn(
            "require a concrete source path before calling one missing", maintain_step(self.body, 3)
        )
        triage = maintain_step(self.body, 5)
        self.assertIn("product gap; record it for the user, keep it out of this PR", triage)


class TestTheMaintainCommandCarriesTheStudioSteps(unittest.TestCase):
    def setUp(self):
        self.body = collapse_whitespace(body_of(read_text(MAINTAIN_COMMAND)))

    def test_step_zero_looks_under_claude_skills(self):
        locate = maintain_step(self.body, 0)
        self.assertIn("`.claude/skills/verify-*/`", locate)
        self.assertIn("/create-verification-skill", locate)

    def test_several_candidates_end_blocked_when_headless(self):
        locate = maintain_step(self.body, 0)
        self.assertRegex(locate, r"-p.{0,200}`blocked`|`blocked`.{0,200}-p")

    def test_step_zero_works_in_a_fresh_worktree_off_origin_main_after_a_fetch(self):
        locate = maintain_step(self.body, 0)
        fetch = locate.find("git fetch origin")
        worktree_add = locate.find("git worktree add --detach")
        self.assertNotEqual(fetch, -1)
        self.assertNotEqual(worktree_add, -1)
        self.assertLess(fetch, worktree_add, "the worktree must be cut after the fetch")
        self.assertRegex(locate, r"git worktree add --detach \S+ origin/<default>")
        self.assertIn("git worktree remove", locate)

    def test_step_zero_makes_no_gh_call(self):
        locate = maintain_step(self.body, 0)
        self.assertNotRegex(locate, r"`gh |\bgh pr\b|\bgh api\b")

    def test_the_source_wave_is_read_only_and_checked(self):
        wave = maintain_step(self.body, 2)
        self.assertIn('subagent_type: "Explore"', wave)
        self.assertIn('"do not edit files"', wave)
        self.assertIn("git status --porcelain", wave)
        self.assertIn("empty", wave)

    def test_index_fixes_wait_until_the_source_wave_check_passes(self):
        self.assertIn("don't make them yet", maintain_step(self.body, 1))
        wave = maintain_step(self.body, 2)
        self.assertLess(
            wave.find("git status --porcelain"),
            wave.find("make the index fixes noted in step 1"),
            "a coordinator index edit before the check would read as a child's edit",
        )

    def test_the_default_branch_is_resolved_from_the_remote_never_assumed(self):
        locate = maintain_step(self.body, 0)
        self.assertIn("git symbolic-ref --short refs/remotes/origin/HEAD", locate)
        self.assertIn("git remote set-head origin --auto", locate)
        self.assertIn("blocked: cannot tell this repository's default branch", locate)
        self.assertNotIn("origin/main", self.body)
        self.assertNotIn("--base main", self.body)

    def test_step_six_stages_everything_before_the_scope_gate(self):
        ship = maintain_step(self.body, 6)
        stage = ship.find("git add -A")
        scope_gate = ship.find("git diff --cached --name-only origin/<default>")
        self.assertNotEqual(stage, -1)
        self.assertNotEqual(scope_gate, -1)
        self.assertLess(stage, scope_gate, "untracked files only show in the gate once staged")
        self.assertIn("is outside edit scope", ship)

    def test_an_open_maintenance_pr_blocks_after_the_coverage_report(self):
        ship = maintain_step(self.body, 6)
        open_pr_check = ship.find("gh pr list --state open --limit 1000 --json number,headRefName")
        self.assertNotEqual(open_pr_check, -1)
        self.assertIn("`verify/maintain-`", ship)
        self.assertIn("earlier maintenance PR #N is still open", ship)
        self.assertLess(ship.find("is outside edit scope"), open_pr_check)
        self.assertRegex(ship, r"coverage and the product-gap report")

    def test_otherwise_it_pushes_one_branch_and_opens_one_ready_pr_into_main(self):
        ship = maintain_step(self.body, 6)
        open_pr_check = ship.find("gh pr list --state open")
        push = ship.find("git push")
        create = ship.find("gh pr create")
        self.assertLess(open_pr_check, push)
        self.assertLess(push, create)
        self.assertIn("verify/maintain-<YYYY-MM-DD>", ship)
        self.assertRegex(ship, r"gh pr create[^`]*--base <default>")
        self.assertNotIn("--draft", ship)
        self.assertIn("ready for review", ship)

    def test_every_run_ends_with_the_outcome_line(self):
        self.assertIn(f"`{OUTCOME_LINE}`", self.body)
        self.assertRegex(self.body, r"last line[^.]*`OUTCOME: ")


def scheduling_section() -> str:
    usage = read_text(USAGE_DOC)
    heading = "## Keeping a verification skill current"
    start = usage.index(heading)
    end = usage.find("\n## ", start + len(heading))
    return usage[start:] if end == -1 else usage[start:end]


class TestTheScheduleRecipe(unittest.TestCase):
    def setUp(self):
        self.section = scheduling_section()

    def test_it_documents_the_hand_run(self):
        self.assertIn("/maintain-verification-skill", self.section)
        self.assertIn("by hand", self.section.lower())

    def test_it_is_a_per_user_launch_agent(self):
        self.assertIn("~/Library/LaunchAgents/", self.section)
        self.assertIn("LaunchDaemon", self.section)
        self.assertRegex(self.section, r"never a LaunchDaemon")

    def test_the_plist_sets_the_keys_launchd_needs(self):
        for key in (
            "StartCalendarInterval",
            "WorkingDirectory",
            "EnvironmentVariables",
            "ProgramArguments",
            "StandardOutPath",
            "StandardErrorPath",
        ):
            with self.subTest(key=key):
                self.assertIn(f"<key>{key}</key>", self.section)
        self.assertRegex(self.section, r"<key>PATH</key>\s*<string>[^<]*/opt/homebrew/bin")

    def test_it_gives_the_claude_line_with_project_settings_only(self):
        line = re.search(r'claude -p "/maintain-verification-skill"[^\n`]*', self.section)
        self.assertIsNotNone(line, "the recipe must show the claude -p command it schedules")
        self.assertIn("--setting-sources project ", line.group(0) + " ")
        self.assertRegex(line.group(0), r"--settings \S+")

    def plist_string(self, key: str) -> str:
        value = re.search(rf"<key>{key}</key>\s*<string>(.*)</string>", self.section)
        self.assertIsNotNone(value, f"the plist must set {key}")
        return value.group(1)

    def test_logs_and_settings_live_outside_the_checkout(self):
        self.assertIn("outside the checkout", self.section)
        repo_root = self.plist_string("WorkingDirectory")
        settings = re.search(r"--settings (\S+)", self.section).group(1)
        for name, path in (
            ("StandardOutPath", self.plist_string("StandardOutPath")),
            ("StandardErrorPath", self.plist_string("StandardErrorPath")),
            ("--settings", settings),
        ):
            with self.subTest(path=name):
                self.assertTrue(path.startswith("/"), f"{name} must be absolute: launchd expands nothing")
                self.assertFalse(path.startswith(repo_root), f"{name} must sit outside the checkout")
                self.assertNotIn(".claude/settings.local.json", path)

    def test_the_settings_file_holds_the_push_and_pr_rules(self):
        for rule in ("git push", "gh pr list", "gh pr create"):
            with self.subTest(rule=rule):
                self.assertIn(f'"Bash({rule} *)"', self.section)

    def test_it_never_puts_the_rules_in_settings_local(self):
        mentions = [
            line for line in self.section.splitlines() if ".claude/settings.local.json" in line
        ]
        self.assertTrue(mentions, "the recipe must warn away from .claude/settings.local.json")
        for line in mentions:
            with self.subTest(line=line[:60]):
                self.assertRegex(line, r"\b(Not|not|never|Never)\b")

    def test_it_warns_that_launchd_runs_a_missed_job_on_wake(self):
        self.assertIn("wakes", self.section)
        self.assertIn("pmset repeat wake", self.section)

    def test_there_is_no_cloud_schedule_recipe(self):
        self.assertNotIn("/schedule", read_text(USAGE_DOC))


class TestTheMaintainCommandIsListed(unittest.TestCase):
    def test_readme_has_a_row(self):
        readme = read_text(REPO_ROOT / "README.md")
        self.assertRegex(readme, r"(?m)^\| `/maintain-verification-skill` \| .{40,}\|$")

    def test_the_utility_slash_commands_table_has_a_row(self):
        usage = read_text(USAGE_DOC)
        table = usage.split("## Utility Slash Commands", 1)[1].split("\n## ", 1)[0]
        self.assertRegex(table, r"(?m)^\| `/maintain-verification-skill` \| .{40,}\|$")


if __name__ == "__main__":
    unittest.main()

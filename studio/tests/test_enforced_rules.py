"""Which of Studio's rules code actually refuses, and which ones only prose asks for.

Studio states its rules in command files and docs, and an agent reading them can skip a step.
Some of those rules also have code behind them that refuses to go on when the rule is broken.
This file keeps the two apart, so anyone can see which rules hold even when an agent ignores
the prose:

- ``ENFORCED`` lists every rule that code refuses. Each row names the rule, where it is stated,
  the function that refuses (the enforcer) and the test that shows the refusal (the proof). The
  suite fails when a cited file is gone or no longer holds the name the row cites, so a renamed
  or deleted refusal cannot leave a row pointing at nothing. A row can also name a phrase from
  the prose step it replaced (``retired_prose``); the suite fails while that phrase is still in
  the file that states the rule, which is how "the prose step is deleted" gets checked.
- ``NOT_YET_ENFORCED`` lists rules with one right answer that nothing refuses yet. Its length
  must equal ``NOT_YET_ENFORCED_COUNT``, a number that only goes down: adding a rule here fails
  until someone raises the number, a one-line edit a reviewer sees going the wrong way, and
  moving a rule into ``ENFORCED`` fails until the number comes down.
- ``JUDGED`` lists judgment rules, the ones where two careful people could disagree about
  whether a piece of work followed them, that a separate agent checks at a step the worker
  cannot skip. Each row names the rule, where it is stated, the prompt that carries it to that
  agent (the judge) and the tracked file holding the judge's measured results, or None while
  nobody has measured it. The suite fails when a cited judge file is gone or no longer holds the
  name the row cites, and when a named results file does not exist. The number of rows with no
  results must equal ``JUDGED_WITHOUT_MEASUREMENT_COUNT``, which only goes down: adding a judge
  nobody has measured fails until someone raises the number where a reviewer sees it.

A rule sentence sits in one list at most. Only a rule with a real judge is in ``JUDGED``. The
judgment rules that only a person looking at the evidence can decide are in no list here; they
stay in Appendix A of ``specs/judged-rules.md``.

What this does not check: that a proving test asserts the right thing, or that a judge judges
well. It checks that the test or the prompt is there under the name the row cites.

Built to ``specs/enforcement-layer.md``, "The enforced-rules table", and
``specs/judged-rules.md``, "The sorting pass".
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


class EnforcedRule(NamedTuple):
    rule: str
    stated_in: str
    enforcer: str
    proof: str
    retired_prose: str | None = None


ENFORCED: list[EnforcedRule] = [
    # 1
    EnforcedRule(
        rule="A `--work-dir` with nothing at that path is refused.",
        stated_in=".claude/commands/forge.md",
        enforcer="studio/impl_loop.py::validate_work_dir",
        proof="studio/tests/test_impl_loop.py::test_validate_work_dir_rejects_a_path_that_does_not_exist",
    ),
    # 2
    EnforcedRule(
        rule="A `--work-dir` that is not inside a git worktree is refused.",
        stated_in=".claude/commands/forge.md",
        enforcer="studio/impl_loop.py::validate_work_dir",
        proof="studio/tests/test_impl_loop.py::test_validate_work_dir_rejects_a_directory_that_is_not_a_worktree",
    ),
    # 3
    EnforcedRule(
        rule="A `--work-dir` that belongs to another repository is refused.",
        stated_in=".claude/commands/forge.md",
        enforcer="studio/impl_loop.py::validate_work_dir",
        proof="studio/tests/test_impl_loop.py::test_validate_work_dir_rejects_a_worktree_of_another_repository",
    ),
    # 4
    EnforcedRule(
        rule="A `--work-dir` holding a character the loop cannot safely quote is refused.",
        stated_in=".claude/commands/forge.md",
        enforcer="studio/impl_loop.py::validate_work_dir",
        proof="studio/tests/test_impl_loop.py::test_validate_work_dir_rejects_a_path_that_would_break_the_quoting",
    ),
    # 5
    EnforcedRule(
        rule="`/forge` does not start on `main` or `master`.",
        stated_in=".claude/commands/forge.md",
        enforcer="studio/impl_loop.py::validate_branch",
        proof="studio/tests/test_impl_loop.py::test_validate_branch_rejects_the_main_branch_even_when_the_tree_is_on_it",
    ),
    # 6
    EnforcedRule(
        rule="`/forge` does not start when the tree is off the planned branch.",
        stated_in=".claude/commands/forge.md",
        enforcer="studio/impl_loop.py::validate_branch",
        proof="studio/tests/test_impl_loop.py::test_validate_branch_rejects_a_tree_that_moved_to_another_branch",
    ),
    # 7
    EnforcedRule(
        rule="`/forge` does not start with uncommitted work in the tree.",
        stated_in=".claude/commands/forge.md",
        enforcer="studio/impl_loop.py::validate_branch",
        proof="studio/tests/test_impl_loop.py::test_validate_branch_rejects_an_uncommitted_edit_and_names_the_file",
        # The command used to tell the agent to run this and judge the tree itself.
        retired_prose="status --porcelain",
    ),
    # 8
    EnforcedRule(
        rule="`/forge` does not start without a test command in the repository's config.",
        stated_in="studio/docs/CLAUDE_CODE_USAGE.md",
        enforcer="studio/impl_loop.py::_require_gate_commands",
        proof="studio/tests/test_impl_loop.py::test_cli_exits_with_the_refusal_and_no_traceback",
    ),
    # 9
    EnforcedRule(
        rule="A bare legacy static-check name in the config is refused.",
        stated_in="studio/docs/CLAUDE_CODE_USAGE.md",
        enforcer="studio/impl_loop.py::_require_gate_commands",
        proof="studio/tests/test_impl_loop.py::test_a_leftover_tool_name_is_refused_and_the_message_says_what_to_write",
    ),
    # 10
    EnforcedRule(
        rule="`record-decisions` refuses an entry with no priority, question or answer.",
        stated_in=".claude/commands/run-phase.md",
        enforcer="studio/run_phase.py::record_decisions",
        proof="studio/tests/test_cli_e2e.py::TestCLIRecordDecisions",
    ),
    # 11
    EnforcedRule(
        rule="`finalize` refuses a run with no advocate file or no contrarian file.",
        stated_in="studio/docs/API.md",
        enforcer="studio/run_phase.py::_validate_artifacts",
        proof="studio/tests/test_run_phase.py::test_finalize_requires_required_artifacts",
    ),
    # 12
    EnforcedRule(
        rule="`finalize` refuses a run with no `summary.md`.",
        stated_in="studio/docs/API.md",
        enforcer="studio/run_phase.py::_validate_artifacts",
        proof="studio/tests/test_cli_e2e.py::test_a_stopped_run_still_needs_the_summary_that_says_why",
    ),
    # 13
    EnforcedRule(
        rule="`finalize` refuses a studio run with no `integrator.md`.",
        stated_in="studio/docs/API.md",
        enforcer="studio/run_phase.py::_validate_artifacts",
        proof="studio/tests/test_run_phase.py::test_finalize_refuses_a_studio_run_with_no_integrator_file",
    ),
    # 14
    EnforcedRule(
        rule="`finalize` refuses a studio run in which no role completed both stances.",
        stated_in="studio/docs/ARCHITECTURE.md",
        enforcer="studio/run_phase.py::_validate_artifacts",
        proof="studio/tests/test_run_phase.py::test_finalize_refuses_a_studio_run_where_no_role_completed_both_stances",
    ),
    # 15
    EnforcedRule(
        rule="`update` does not overwrite local edits without `--force`.",
        stated_in=".claude/commands/studio-update.md",
        enforcer="studio/install.py::update_studio",
        proof="studio/tests/test_install.py::test_update_blocked_on_local_modification",
    ),
    # 16
    EnforcedRule(
        rule="`check-install` exits non-zero when the source checkout is behind its remote.",
        stated_in=".claude/commands/studio-update.md",
        enforcer="studio/run_phase.py::_do_check_install",
        proof="studio/tests/test_install.py::test_handler_exits_nonzero_on_stale_source",
    ),
    # 17
    EnforcedRule(
        rule="`setup` refuses an unknown role pack.",
        stated_in=".claude/commands/studio-setup.md",
        enforcer="studio/setup.py::apply_role_pack",
        proof="studio/tests/test_setup.py::test_invalid_pack_raises",
    ),
    # 18
    EnforcedRule(
        rule="`setup` refuses an unknown role-override field.",
        stated_in=".claude/commands/studio-setup.md",
        enforcer="studio/setup.py::apply_role_customization",
        proof="studio/tests/test_setup.py::test_validates_fields",
    ),
    # 19
    EnforcedRule(
        rule="`setup` refuses a persona key in the wrong place.",
        stated_in=".claude/commands/studio-setup.md",
        enforcer="studio/persona_overrides.py::validate_persona_overrides",
        proof="studio/tests/test_setup.py::test_invalid_customization_propagates",
    ),
    # 20
    EnforcedRule(
        rule="`setup` never overwrites an existing `implementation_loop.toml`.",
        stated_in=".claude/commands/studio-setup.md",
        enforcer="studio/setup.py::apply_implementation_loop_config",
        proof="studio/tests/test_setup.py::test_never_overwrites_a_hand_written_file",
    ),
    # 21: the enforcer is itself a test, so it is its own proof.
    EnforcedRule(
        rule="Studio's code imports only the standard library, plus `tomli` on Python 3.10.",
        stated_in="CLAUDE.md",
        enforcer="studio/tests/test_stdlib_only.py::test_every_studio_module_imports_only_the_standard_library",
        proof="studio/tests/test_stdlib_only.py::test_every_studio_module_imports_only_the_standard_library",
    ),
    # 22 to 28: the spec rules live in the test suite today. The rule function is the enforcer
    # and the test that feeds it a broken spec is the proof.
    EnforcedRule(
        rule="A spec's `status` is one of draft, approved, shipped.",
        stated_in=".claude/commands/spec.md",
        enforcer="studio/tests/test_spec_verification.py::_violations",
        proof="studio/tests/test_spec_verification.py::test_unknown_status_fails",
    ),
    EnforcedRule(
        rule="An approved spec with a Verification section has an evidence file.",
        stated_in=".claude/commands/spec.md",
        enforcer="studio/tests/test_spec_verification.py::_violations",
        proof="studio/tests/test_spec_verification.py::test_approved_with_missing_results_file_fails",
    ),
    EnforcedRule(
        rule=(
            "An approved spec with a Verification section has a `verification_due` date "
            "that has not passed."
        ),
        stated_in=".claude/commands/spec.md",
        enforcer="studio/tests/test_spec_verification.py::_violations",
        proof="studio/tests/test_spec_verification.py::test_approved_past_its_due_date_fails",
    ),
    EnforcedRule(
        rule="A shipped spec's evidence file is filled in.",
        stated_in=".claude/commands/spec.md",
        enforcer="studio/tests/test_spec_verification.py::_violations",
        proof="studio/tests/test_spec_verification.py::test_shipped_with_placeholders_fails",
    ),
    EnforcedRule(
        rule="A shipped spec has `shipped_impact` and `shipped_changed`.",
        stated_in=".claude/commands/spec.md",
        enforcer="studio/tests/test_spec_verification.py::_violations",
        proof="studio/tests/test_spec_verification.py::test_shipped_without_an_outcome_line_fails",
    ),
    EnforcedRule(
        rule="An approved spec's Build Plan has the heading shape and at least one criterion per unit.",
        stated_in=".claude/commands/spec.md",
        enforcer="studio/tests/test_spec_verification.py::_build_plan_problems",
        proof="studio/tests/test_spec_verification.py::test_approved_with_a_unit_holding_no_criteria_fails",
    ),
    EnforcedRule(
        rule="A `unit_id` is unique across the repository's specs.",
        stated_in=".claude/commands/spec.md",
        enforcer="studio/tests/test_spec_verification.py::_duplicate_unit_ids",
        proof="studio/tests/test_spec_verification.py::test_two_specs_planning_the_same_id_is_caught",
    ),
]


NOT_YET_ENFORCED: list[str] = [
    "A push to a branch whose pull request already merged.",
    "A run is not finalized, and a scoped run does not brief its next agent, while a raised decision is unanswered.",
    "An unscoped run pauses before its next agent while a raised decision is unanswered.",
    "A `/spec` run commits only the spec and opens its pull request at `status: draft`.",
    "A `unit_id` is not renamed after approval.",
    "A unit carries three to six criteria.",
    "`/offload --apply` and `--verify` do what they say.",
    "`/message-draft` runs its linter before handing over a draft.",
    "`/studio-update` never passes `--force` on its own.",
    "Each debate iteration has one advocate file and one contrarian file.",
    "`integrator.md` carries its three sections.",
    "The criteria the editor graded are the spec's own words.",
    "A unit's criteria come from its spec, or the run stops.",
    "Criteria with the editor switched off stop the run.",
    "The finalize verdict is the debate's own.",
    "A unit is called clean only if Studio ran the tests itself.",
    "`/forge`'s commits land on its branch.",
    "No worktree removal deletes run artifacts that exist nowhere else.",
    "An agent asks before merging.",
    "Pull requests target the main branch.",
    # The 32 entries from the sort in specs/judged-rules.md, Appendix A, in its order.
    "`/forge` does not build against a spec that is not approved without the user's go-ahead on record.",
    "The static-check commands `/forge` passes have their paths filled in by code, and a command with no paths is dropped.",
    "`/forge` and `/spec` print their plan from code, and `--plan` starts nothing.",
    "The loop script `/forge` launches is the work tree's own copy or a byte-identical one.",
    "The grades in a `/forge` report are printed by code from the loop's return.",
    "A spec's path is resolved by code, and an existing spec is revised in place.",
    "A spec is not written from a debate that ended REJECTED without the user's go-ahead on record.",
    "A spec has every required section, including the plain-language one and a diagram.",
    "A spec that is not shipped has empty `shipped_*` fields.",
    "A spec becomes approved only in a commit that changes nothing else, after its pull request merged.",
    "The pass criterion in an evidence file is the spec's own sentence.",
    "An evidence file is tracked by git, not ignored.",
    "A `/spec` run's debate is finalized before its spec is committed.",
    "A debate's agents run in the order and with the inputs code sets: one agent per stance, the contrarian reading only the advocate's file, a briefing before each.",
    "A debate does not start its first agent before its pre-flight questions have answers on record.",
    "An approved run that produces a deliverable has an `implementation.md` before it is finalized.",
    "A stance file over its scope's word cap is refused.",
    "A studio run has a current `S2-brief.md` before each third role is briefed.",
    "A `/message-draft` draft is saved outside the repository under a new name and handed over by code.",
    "`/studio-update` and `/studio-setup` stop and say what is next themselves: up to date, restart needed, not installed, or status only.",
    "`/handoff` picks its mode and its directory in code and prints the resume command.",
    "A handoff note's branch, commit and pull-request state match git and GitHub when it is written.",
    "`/smoke` takes its profile from config in code, names it, reports an ambiguous stack, and stops when the build fails.",
    "`/smoke` hands over only after its health check answers.",
    "`/detest` and `/unstale` run the suite before and after their fixes themselves.",
    "The audit agents in `/detest`, `/unstale` and `/offload` run without edit tools.",
    "A `/detest` run changes only test files, adds no dependency, and leaves no mutation behind.",
    "`/unstale` takes its profile from config in code and names it.",
    "An agent asks before closing an issue or deleting a tracking file.",
    "An `/unstale` run creates no new document and only adds to the changelog.",
    "The counts the docs state match the code.",
    "An approved spec is a tracked file under the specs directory.",
]

# Rose once, on purpose, from 20 to 52 when specs/judged-rules.md sorted the rules an audit found
# unchecked. This number only goes down from here.
NOT_YET_ENFORCED_COUNT = 52


class JudgedRule(NamedTuple):
    rule: str
    stated_in: str
    judge: str
    results: str | None = None


JUDGED: list[JudgedRule] = [
    # The /forge editor's prompt asks it to grade each criterion and to set mvi_verdict only when
    # the unit is usable and every criterion passes. It also prints the contrarian mandate, whose
    # "Default to deletion" and "Cut concepts, not clarity" lines carry the next two rules.
    JudgedRule(
        rule="A unit passes only when every acceptance criterion of its spec holds in the code.",
        stated_in=".claude/commands/forge.md",
        judge=".claude/workflows/implementation-loop.js::editorPrompt",
    ),
    JudgedRule(
        rule="Every unit ends in something usable.",
        stated_in="CLAUDE.md",
        judge=".claude/workflows/implementation-loop.js::editorPrompt",
    ),
    JudgedRule(
        rule="No unrequested features, abstractions or config.",
        stated_in="CLAUDE.md",
        judge=".claude/workflows/implementation-loop.js::editorPrompt",
    ),
    JudgedRule(
        rule="Code is written for humans.",
        stated_in="CLAUDE.md",
        judge=".claude/workflows/implementation-loop.js::editorPrompt",
    ),
    # The debate contrarian. A scoped run, which is what /spec runs, builds its prompt in
    # generate_scope_prompt: it tells the contrarian to flag what the advocate assumed but is
    # unsettled, asks every depth deliverable to end in a testable condition, and treats
    # decisions.md as hard constraints. The quote-first rule is in CONTRARIAN_MANDATE, which that
    # prompt includes; the finding verifier checks the same rule afterwards, and this field holds
    # one judge, so it names the contrarian's.
    JudgedRule(
        rule="Pre-flight surfaces what is unsettled; an unknown is never papered over.",
        stated_in=".claude/commands/spec.md",
        judge="studio/scopes.py::generate_scope_prompt",
    ),
    JudgedRule(
        rule="Criteria are checkable from code.",
        stated_in=".claude/commands/spec.md",
        judge="studio/scopes.py::generate_scope_prompt",
    ),
    JudgedRule(
        rule="An index summary is not evidence; quote the file.",
        stated_in=".claude/commands/spec.md",
        judge="studio/scopes.py::CONTRARIAN_MANDATE",
    ),
    JudgedRule(
        rule="Settled decisions are hard constraints.",
        stated_in=".claude/commands/run-phase.md",
        judge="studio/scopes.py::generate_scope_prompt",
    ),
]

JUDGED_WITHOUT_MEASUREMENT_COUNT = 8  # this number only goes down


# ---------------------------------------------------------------------------
# The checks. Each takes its rows or list as arguments, so the tests further down can feed it
# a made-up bad row and watch it complain.
# ---------------------------------------------------------------------------


def _citation_problem(rule: str, field_name: str, citation: str, root: Path) -> str | None:
    """Why ``citation`` (written ``file::name``) does not point at a real name, or None."""
    file_part, separator, name = citation.partition("::")
    if not separator or not file_part.strip() or not name.strip():
        return f"{rule!r}: {field_name} {citation!r} is not written as file::name."
    cited_file = root / file_part
    if not cited_file.is_file():
        return f"{rule!r}: {field_name} file {file_part} does not exist."
    text = cited_file.read_text(encoding="utf-8")
    # A whole-word match, so a longer name that merely starts with the cited one, such as
    # test_x_fails_twice standing in for a deleted test_x_fails, does not count.
    if not re.search(rf"\b{re.escape(name)}\b", text):
        return f"{rule!r}: {field_name} file {file_part} no longer contains {name}."
    return None


def citation_problems(rows: list[EnforcedRule], root: Path) -> list[str]:
    """Every row that is missing a field, or cites a file or name that is not there."""
    problems: list[str] = []
    for row in rows:
        if not row.rule.strip():
            problems.append(f"A row citing {row.enforcer!r} has no rule sentence.")
            continue
        if not (root / row.stated_in).is_file():
            problems.append(f"{row.rule!r}: stated_in file {row.stated_in!r} does not exist.")
        for field_name in ("enforcer", "proof"):
            problem = _citation_problem(row.rule, field_name, getattr(row, field_name), root)
            if problem:
                problems.append(problem)
    return problems


def unretired_prose_problems(rows: list[EnforcedRule], root: Path) -> list[str]:
    """Every row whose retired prose is still in the file that states its rule."""
    problems: list[str] = []
    for row in rows:
        if row.retired_prose is None:
            continue
        stated_in_file = root / row.stated_in
        if not stated_in_file.is_file():
            continue  # citation_problems already reports a missing stated_in file.
        if row.retired_prose in stated_in_file.read_text(encoding="utf-8"):
            problems.append(
                f"{row.rule!r}: {row.stated_in} still says {row.retired_prose!r}. "
                f"Code enforces this rule now, so delete the prose step it replaced."
            )
    return problems


def count_problem(entries: list[str], expected_count: int) -> str | None:
    """Why the list's length differs from the number beside it, or None."""
    actual_count = len(entries)
    if actual_count > expected_count:
        return (
            f"NOT_YET_ENFORCED has {actual_count} entries but NOT_YET_ENFORCED_COUNT is "
            f"{expected_count}. Raising the count means one more rule nothing refuses; "
            f"enforce the rule instead, or raise the count on purpose where a reviewer sees it."
        )
    if actual_count < expected_count:
        return (
            f"NOT_YET_ENFORCED has {actual_count} entries but NOT_YET_ENFORCED_COUNT is "
            f"{expected_count}. A rule left the list: lower the count to {actual_count}."
        )
    return None


def judge_citation_problems(rows: list[JudgedRule], root: Path) -> list[str]:
    """Every judged row whose stated_in file is gone, or whose judge is not where it says."""
    problems: list[str] = []
    for row in rows:
        if not (root / row.stated_in).is_file():
            problems.append(f"{row.rule!r}: stated_in file {row.stated_in!r} does not exist.")
        problem = _citation_problem(row.rule, "judge", row.judge, root)
        if problem:
            problems.append(problem)
    return problems


def missing_results_problems(rows: list[JudgedRule], root: Path) -> list[str]:
    """Every judged row that names a results file nobody can find."""
    problems: list[str] = []
    for row in rows:
        if row.results is None:
            continue
        if not (root / row.results).is_file():
            problems.append(f"{row.rule!r}: results file {row.results!r} does not exist.")
    return problems


def unmeasured_count_problem(rows: list[JudgedRule], expected_count: int) -> str | None:
    """Why the number of judged rows with no results differs from the number beside it, or None."""
    unmeasured_count = sum(1 for row in rows if row.results is None)
    if unmeasured_count > expected_count:
        return (
            f"JUDGED has {unmeasured_count} rows with no results but "
            f"JUDGED_WITHOUT_MEASUREMENT_COUNT is {expected_count}. A judge nobody has measured "
            f"was added: measure it and name its results file, or raise the count on purpose "
            f"where a reviewer sees it."
        )
    if unmeasured_count < expected_count:
        return (
            f"JUDGED has {unmeasured_count} rows with no results but "
            f"JUDGED_WITHOUT_MEASUREMENT_COUNT is {expected_count}. A judge was measured or "
            f"left the list: lower the count to {unmeasured_count}."
        )
    return None


def rules_in_more_than_one_list(lists: dict[str, list[str]]) -> list[str]:
    """Every rule sentence that appears in more than one of the named lists."""
    list_names_by_rule: dict[str, list[str]] = {}
    for list_name, rules in lists.items():
        for rule in rules:
            names = list_names_by_rule.setdefault(rule, [])
            if list_name not in names:
                names.append(list_name)
    return [
        f"{rule!r} is in {' and '.join(list_names)}. A rule belongs to one list."
        for rule, list_names in list_names_by_rule.items()
        if len(list_names) > 1
    ]


# ---------------------------------------------------------------------------
# The real table.
# ---------------------------------------------------------------------------


def test_every_enforced_row_cites_an_enforcer_and_a_proof_that_are_still_there():
    problems = citation_problems(ENFORCED, REPO_ROOT)
    assert not problems, "\n".join(problems)


def test_no_retired_prose_is_left_in_the_file_that_states_its_rule():
    problems = unretired_prose_problems(ENFORCED, REPO_ROOT)
    assert not problems, "\n".join(problems)


def test_the_not_yet_enforced_list_is_exactly_as_long_as_its_count():
    problem = count_problem(NOT_YET_ENFORCED, NOT_YET_ENFORCED_COUNT)
    assert problem is None, problem


def test_every_judged_row_cites_a_judge_that_is_still_there():
    problems = judge_citation_problems(JUDGED, REPO_ROOT)
    assert not problems, "\n".join(problems)


def test_every_results_file_a_judged_row_names_exists():
    problems = missing_results_problems(JUDGED, REPO_ROOT)
    assert not problems, "\n".join(problems)


def test_the_unmeasured_judges_are_exactly_as_many_as_their_count():
    problem = unmeasured_count_problem(JUDGED, JUDGED_WITHOUT_MEASUREMENT_COUNT)
    assert problem is None, problem


def test_no_rule_sentence_is_in_more_than_one_list():
    problems = rules_in_more_than_one_list(
        {
            "ENFORCED": [row.rule for row in ENFORCED],
            "NOT_YET_ENFORCED": NOT_YET_ENFORCED,
            "JUDGED": [row.rule for row in JUDGED],
        }
    )
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# The checks themselves, fed made-up rows in a temporary directory, so a check that stopped
# complaining would fail here rather than quietly pass the real table.
# ---------------------------------------------------------------------------


def _write(root: Path, relative_path: str, text: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sound_row(root: Path) -> EnforcedRule:
    """A row whose every cited file exists and holds its name."""
    _write(root, "docs/rules.md", "The rule, stated in prose.\n")
    _write(root, "code/enforcer.py", "def refuse_bad_input():\n    raise ValueError\n")
    _write(root, "tests/test_enforcer.py", "def test_bad_input_is_refused():\n    pass\n")
    return EnforcedRule(
        rule="Bad input is refused.",
        stated_in="docs/rules.md",
        enforcer="code/enforcer.py::refuse_bad_input",
        proof="tests/test_enforcer.py::test_bad_input_is_refused",
    )


def test_a_sound_row_reports_nothing(tmp_path):
    assert citation_problems([_sound_row(tmp_path)], tmp_path) == []


@pytest.mark.parametrize("field_name", ["enforcer", "proof"])
def test_a_cited_file_that_is_gone_is_reported(tmp_path, field_name):
    row = _sound_row(tmp_path)
    cited_file = getattr(row, field_name).partition("::")[0]
    (tmp_path / cited_file).unlink()

    problems = citation_problems([row], tmp_path)

    assert problems == [f"'Bad input is refused.': {field_name} file {cited_file} does not exist."]


@pytest.mark.parametrize("field_name", ["enforcer", "proof"])
def test_a_cited_name_the_file_no_longer_contains_is_reported(tmp_path, field_name):
    row = _sound_row(tmp_path)
    cited_file, _, cited_name = getattr(row, field_name).partition("::")
    _write(tmp_path, cited_file, "def something_renamed():\n    pass\n")

    problems = citation_problems([row], tmp_path)

    assert problems == [
        f"'Bad input is refused.': {field_name} file {cited_file} no longer contains {cited_name}."
    ]


def test_a_longer_name_does_not_stand_in_for_the_cited_one(tmp_path):
    row = _sound_row(tmp_path)
    _write(tmp_path, "tests/test_enforcer.py", "def test_bad_input_is_refused_twice():\n    pass\n")

    problems = citation_problems([row], tmp_path)

    assert len(problems) == 1
    assert "no longer contains test_bad_input_is_refused" in problems[0]


def test_a_citation_without_a_name_after_the_separator_is_reported(tmp_path):
    row = _sound_row(tmp_path)._replace(enforcer="code/enforcer.py")

    problems = citation_problems([row], tmp_path)

    assert problems == ["'Bad input is refused.': enforcer 'code/enforcer.py' is not written as file::name."]


def test_a_stated_in_file_that_is_gone_is_reported(tmp_path):
    row = _sound_row(tmp_path)._replace(stated_in="docs/deleted.md")

    problems = citation_problems([row], tmp_path)

    assert problems == ["'Bad input is refused.': stated_in file 'docs/deleted.md' does not exist."]


def test_a_row_with_no_rule_sentence_is_reported(tmp_path):
    row = _sound_row(tmp_path)._replace(rule="  ")

    problems = citation_problems([row], tmp_path)

    assert len(problems) == 1
    assert "has no rule sentence" in problems[0]


def test_retired_prose_still_in_its_stated_in_file_is_reported(tmp_path):
    row = _sound_row(tmp_path)._replace(retired_prose="check it by hand")
    _write(tmp_path, "docs/rules.md", "Before you start, check it by hand.\n")

    problems = unretired_prose_problems([row], tmp_path)

    assert len(problems) == 1
    assert "docs/rules.md still says 'check it by hand'" in problems[0]


def test_retired_prose_that_was_deleted_reports_nothing(tmp_path):
    row = _sound_row(tmp_path)._replace(retired_prose="check it by hand")

    assert unretired_prose_problems([row], tmp_path) == []


def test_a_list_longer_than_its_count_is_reported():
    problem = count_problem(["one rule", "another rule", "a third rule"], expected_count=2)

    assert problem is not None
    assert "has 3 entries but NOT_YET_ENFORCED_COUNT is 2" in problem


def test_a_list_shorter_than_its_count_is_reported():
    problem = count_problem(["one rule"], expected_count=2)

    assert problem is not None
    assert "lower the count to 1" in problem


def test_a_list_exactly_as_long_as_its_count_reports_nothing():
    assert count_problem(["one rule", "another rule"], expected_count=2) is None


def _sound_judged_row(root: Path) -> JudgedRule:
    """A judged row whose stated_in and judge files exist and hold what the row cites."""
    _write(root, "docs/rules.md", "The judgment rule, stated in prose.\n")
    _write(root, "prompts/judge.py", "def judge_prompt():\n    return 'Judge the work.'\n")
    return JudgedRule(
        rule="The work is judged.",
        stated_in="docs/rules.md",
        judge="prompts/judge.py::judge_prompt",
    )


def test_a_sound_judged_row_reports_nothing(tmp_path):
    row = _sound_judged_row(tmp_path)

    assert judge_citation_problems([row], tmp_path) == []
    assert missing_results_problems([row], tmp_path) == []


def test_a_judge_file_that_is_gone_is_reported(tmp_path):
    row = _sound_judged_row(tmp_path)
    (tmp_path / "prompts/judge.py").unlink()

    problems = judge_citation_problems([row], tmp_path)

    assert problems == ["'The work is judged.': judge file prompts/judge.py does not exist."]


def test_a_judge_name_the_file_no_longer_contains_is_reported(tmp_path):
    row = _sound_judged_row(tmp_path)
    _write(tmp_path, "prompts/judge.py", "def renamed_prompt():\n    return 'Judge the work.'\n")

    problems = judge_citation_problems([row], tmp_path)

    assert problems == [
        "'The work is judged.': judge file prompts/judge.py no longer contains judge_prompt."
    ]


def test_a_judged_stated_in_file_that_is_gone_is_reported(tmp_path):
    row = _sound_judged_row(tmp_path)._replace(stated_in="docs/deleted.md")

    problems = judge_citation_problems([row], tmp_path)

    assert problems == ["'The work is judged.': stated_in file 'docs/deleted.md' does not exist."]


def test_a_results_file_that_does_not_exist_is_reported(tmp_path):
    row = _sound_judged_row(tmp_path)._replace(results="results/judge.md")

    problems = missing_results_problems([row], tmp_path)

    assert problems == ["'The work is judged.': results file 'results/judge.md' does not exist."]


def test_a_results_file_that_exists_reports_nothing(tmp_path):
    row = _sound_judged_row(tmp_path)._replace(results="results/judge.md")
    _write(tmp_path, "results/judge.md", "Measured.\n")

    assert missing_results_problems([row], tmp_path) == []


def test_more_unmeasured_judges_than_the_count_is_reported(tmp_path):
    row = _sound_judged_row(tmp_path)

    problem = unmeasured_count_problem([row, row._replace(rule="Another rule.")], expected_count=1)

    assert problem is not None
    assert "JUDGED has 2 rows with no results but JUDGED_WITHOUT_MEASUREMENT_COUNT is 1" in problem


def test_fewer_unmeasured_judges_than_the_count_is_reported(tmp_path):
    row = _sound_judged_row(tmp_path)

    problem = unmeasured_count_problem([row], expected_count=2)

    assert problem is not None
    assert "lower the count to 1" in problem


def test_a_measured_judge_is_not_counted_as_unmeasured(tmp_path):
    unmeasured_row = _sound_judged_row(tmp_path)
    measured_row = unmeasured_row._replace(rule="A measured rule.", results="results/judge.md")

    assert unmeasured_count_problem([unmeasured_row, measured_row], expected_count=1) is None


def test_one_sentence_in_two_lists_is_reported():
    problems = rules_in_more_than_one_list(
        {
            "ENFORCED": ["Bad input is refused."],
            "NOT_YET_ENFORCED": ["Something nothing refuses yet."],
            "JUDGED": ["Bad input is refused."],
        }
    )

    assert problems == ["'Bad input is refused.' is in ENFORCED and JUDGED. A rule belongs to one list."]


def test_lists_that_share_no_sentence_report_nothing():
    problems = rules_in_more_than_one_list(
        {
            "ENFORCED": ["Bad input is refused."],
            "NOT_YET_ENFORCED": ["Something nothing refuses yet."],
            "JUDGED": ["The work is judged."],
        }
    )

    assert problems == []

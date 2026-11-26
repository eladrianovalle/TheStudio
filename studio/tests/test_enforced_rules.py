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

import ast
import re
from pathlib import Path
from typing import NamedTuple

import pytest

from install import PACK_DOC_GLOB, SLASH_COMMANDS, SOURCE_FILES

REPO_ROOT = Path(__file__).resolve().parents[2]


class EnforcedRule(NamedTuple):
    rule: str
    stated_in: str
    enforcer: str
    proof: str
    retired_prose: str | None = None


ENFORCED: list[EnforcedRule] = [
    EnforcedRule(
        rule="Agents write zero comments in code, including tests.",
        stated_in="CLAUDE.md",
        enforcer="studio/code_comments.py::check_trees",
        proof="studio/tests/test_code_comments.py::test_new_comment_blocks_delivery",
    ),
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
        stated_in=".claude/commands/forge.md",
        enforcer="studio/impl_loop.py::_require_gate_commands",
        proof="studio/tests/test_impl_loop.py::test_cli_exits_with_the_refusal_and_no_traceback",
    ),
    # 9
    EnforcedRule(
        rule="A bare legacy static-check name in the config is refused.",
        stated_in=".claude/commands/forge.md",
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
        stated_in=".claude/commands/run-phase.md",
        enforcer="studio/run_phase.py::_validate_artifacts",
        proof="studio/tests/test_run_phase.py::test_finalize_requires_required_artifacts",
    ),
    # 12
    EnforcedRule(
        rule="`finalize` refuses a run with no `summary.md`.",
        stated_in=".claude/commands/run-phase.md",
        enforcer="studio/run_phase.py::_validate_artifacts",
        proof="studio/tests/test_cli_e2e.py::test_a_stopped_run_still_needs_the_summary_that_says_why",
    ),
    # 13
    EnforcedRule(
        rule="`finalize` refuses a studio run with no `integrator.md`.",
        stated_in=".claude/commands/run-studio-phase.md",
        enforcer="studio/run_phase.py::_validate_artifacts",
        proof="studio/tests/test_run_phase.py::test_finalize_refuses_a_studio_run_with_no_integrator_file",
    ),
    # 14
    EnforcedRule(
        rule="`finalize` refuses a studio run in which no role completed both stances.",
        stated_in=".claude/commands/run-studio-phase.md",
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
    EnforcedRule(
        rule="An exception past its `until=` date fails the suite.",
        stated_in=".claude/commands/correct.md",
        enforcer="studio/tests/test_exception_expiry.py::expired_exceptions",
        proof="studio/tests/test_exception_expiry.py::test_a_planted_exception_past_its_date_fails_with_fix_and_see",
    ),
    EnforcedRule(
        rule="An asset report that breaks its pack's contract fails `check-packs`.",
        stated_in="studio/packs/game/ASSET_PIPELINE.md",
        enforcer="studio/packs.py::report_problems",
        proof="studio/tests/test_packs.py::test_metric_above_its_max_fails",
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
    "The suite runs in CI on Python 3.10, the oldest version Studio supports.",
    "A pull request that changes a command file or a CLI subcommand also changes the usage docs.",
]

# Rose once, on purpose, from 20 to 52 when specs/judged-rules.md sorted the rules an audit found
# unchecked. This number only goes down from here.
NOT_YET_ENFORCED_COUNT = 54


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
        results="studio/evals/forge_editor/results.json",
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
    # decisions.md as hard constraints.
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
        rule="Settled decisions are hard constraints.",
        stated_in=".claude/commands/run-phase.md",
        judge="studio/scopes.py::generate_scope_prompt",
    ),
]

JUDGED_WITHOUT_MEASUREMENT_COUNT = 6  # this number only goes down

REFUSALS_WITHOUT_FIX_COUNT = 20


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


def count_problem(
    entries: list[str], expected_count: int, list_name: str, count_name: str
) -> str | None:
    """Why the list's length differs from the number beside it, or None."""
    actual_count = len(entries)
    if actual_count > expected_count:
        return (
            f"{list_name} has {actual_count} entries but {count_name} is {expected_count}. "
            f"The count only goes down: fix the new entry instead, or raise the count on "
            f"purpose where a reviewer sees it."
        )
    if actual_count < expected_count:
        return (
            f"{list_name} has {actual_count} entries but {count_name} is {expected_count}. "
            f"An entry left the list: lower the count to {actual_count}."
        )
    return None


def unshipped_stated_in_problems(rows: list[EnforcedRule]) -> list[str]:
    studio_dir = REPO_ROOT / "studio"
    shipped_pack_docs = {
        f"studio/{path.relative_to(studio_dir).as_posix()}" for path in studio_dir.glob(PACK_DOC_GLOB)
    }
    shipped_rule_files = {
        "CLAUDE.md",
        *(f".claude/commands/{name}" for name in SLASH_COMMANDS),
        *shipped_pack_docs,
    }
    problems: list[str] = []
    for row in rows:
        enforcer_file = row.enforcer.partition("::")[0]
        if enforcer_file.removeprefix("studio/") not in SOURCE_FILES:
            continue
        if row.stated_in not in shipped_rule_files:
            problems.append(
                f"{row.rule!r}: {row.enforcer} runs in installed repositories, which have no "
                f"{row.stated_in}. Cite CLAUDE.md, a shipped pack doc, or a command file in "
                f"SLASH_COMMANDS that states the rule."
            )
    return problems


def _proof_source(proof: str, root: Path) -> str:
    proof_file, _, proof_name = proof.partition("::")
    path = root / proof_file
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    definitions = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, definitions) and node.name == proof_name:
            first_line = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
            return "\n".join(text.splitlines()[first_line - 1:node.end_lineno])
    return ""


def rows_whose_proof_lacks_fix_and_see(rows: list[EnforcedRule], root: Path) -> list[str]:
    lacking: list[str] = []
    for row in rows:
        source = _proof_source(row.proof, root)
        if "Fix:" not in source or f"See {row.stated_in}" not in source:
            lacking.append(row.rule)
    return lacking


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


MEMORY_SORT_SPEC = REPO_ROOT / "specs" / "correct-rules.md"
MEMORY_SORT_HEADING = "## Appendix A: the memory sort"
MEMORY_SORT_RULE_LABELS = ("listed", "by design", "proxy", "judge", "person")
MEMORY_SORT_TOTAL_LABELS = (*MEMORY_SORT_RULE_LABELS, "fact", "personal")
MEMORY_SORT_LIST_BY_LABEL = {
    "by design": "NOT_YET_ENFORCED",
    "proxy": "NOT_YET_ENFORCED",
    "judge": "JUDGED",
}


class MemorySortRow(NamedTuple):
    rule: str
    label: str
    memories: int
    goes_to: str


def memory_sort_rows(appendix: str) -> list[MemorySortRow]:
    rows: list[MemorySortRow] = []
    for line in appendix.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 4 and cells[2].isdigit():
            rows.append(MemorySortRow(cells[0], cells[1], int(cells[2]), cells[3]))
    return rows


def memory_sort_totals(appendix: str) -> tuple[dict[str, int], int] | None:
    match = re.search(r"^Totals: (.+); (\d+) in all\.$", appendix, re.MULTILINE)
    if match is None:
        return None
    counts: dict[str, int] = {}
    for part in match.group(1).split(", "):
        number, _, label = part.partition(" ")
        counts[label] = int(number)
    return counts, int(match.group(2))


def memory_sort_row_problem(row: MemorySortRow, lists: dict[str, list[str]]) -> str | None:
    if row.label not in MEMORY_SORT_RULE_LABELS:
        return f"{row.rule!r}: {row.label!r} is not one of {', '.join(MEMORY_SORT_RULE_LABELS)}."
    required_list = MEMORY_SORT_LIST_BY_LABEL.get(row.label)
    if required_list is not None and row.goes_to != required_list:
        return f"{row.rule!r} is labelled {row.label}, so it goes to {required_list}, not {row.goes_to}."
    if row.label == "listed" and row.goes_to not in lists:
        return f"{row.rule!r} is labelled listed, but {row.goes_to} is not one of the lists."
    if row.label == "person" and row.goes_to in lists:
        return f"{row.rule!r} is for a person, so it stays out of {row.goes_to}."
    if required_list is not None and row.rule not in lists[required_list] + lists["ENFORCED"]:
        return f"{row.rule!r} goes to {required_list}, but {required_list} does not hold that sentence."
    return None


def memory_sort_problems(spec_text: str, lists: dict[str, list[str]]) -> list[str]:
    appendix = spec_text.partition(MEMORY_SORT_HEADING)[2]
    if not appendix:
        return [f"The spec has no {MEMORY_SORT_HEADING!r} section."]
    problems: list[str] = []
    if "feedback_" in appendix:
        problems.append("The memory sort names a memory file. State the rule, not where it came from.")
    rows = memory_sort_rows(appendix)
    for row in rows:
        problem = memory_sort_row_problem(row, lists)
        if problem:
            problems.append(problem)
    totals = memory_sort_totals(appendix)
    if totals is None:
        problems.append("The memory sort has no line reading 'Totals: <n> <label>, ...; <n> in all.'")
        return problems
    counts, stated_total = totals
    if tuple(counts) != MEMORY_SORT_TOTAL_LABELS:
        problems.append(
            f"The totals name {', '.join(counts)}; they should name "
            f"{', '.join(MEMORY_SORT_TOTAL_LABELS)}, in that order."
        )
    if sum(counts.values()) != stated_total:
        problems.append(f"The totals add up to {sum(counts.values())}, not the {stated_total} they state.")
    for label in MEMORY_SORT_RULE_LABELS:
        memories_in_rows = sum(row.memories for row in rows if row.label == label)
        if memories_in_rows != counts.get(label, 0):
            problems.append(
                f"The {label} rows stand for {memories_in_rows} memories, but the totals say "
                f"{counts.get(label, 0)}."
            )
    return problems


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
    problem = count_problem(
        NOT_YET_ENFORCED, NOT_YET_ENFORCED_COUNT, "NOT_YET_ENFORCED", "NOT_YET_ENFORCED_COUNT"
    )
    assert problem is None, problem


def test_every_refusal_that_runs_in_an_installed_repository_cites_a_file_that_ships():
    problems = unshipped_stated_in_problems(ENFORCED)
    assert not problems, "\n".join(problems)


def test_the_refusals_whose_proof_lacks_fix_and_see_are_exactly_as_many_as_their_count():
    lacking = rows_whose_proof_lacks_fix_and_see(ENFORCED, REPO_ROOT)
    problem = count_problem(
        lacking,
        REFUSALS_WITHOUT_FIX_COUNT,
        "The ENFORCED rows whose proof lacks Fix: and See <stated_in>",
        "REFUSALS_WITHOUT_FIX_COUNT",
    )
    assert problem is None, "\n".join([problem or "", *lacking])


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


def test_the_memory_sort_lands_every_checkable_rule_in_its_list_and_its_totals_add_up():
    problems = memory_sort_problems(
        MEMORY_SORT_SPEC.read_text(encoding="utf-8"),
        {
            "ENFORCED": [row.rule for row in ENFORCED],
            "NOT_YET_ENFORCED": NOT_YET_ENFORCED,
            "JUDGED": [row.rule for row in JUDGED],
        },
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
    problem = count_problem(
        ["one rule", "another rule", "a third rule"], 2, "NOT_YET_ENFORCED", "NOT_YET_ENFORCED_COUNT"
    )

    assert problem is not None
    assert "NOT_YET_ENFORCED has 3 entries but NOT_YET_ENFORCED_COUNT is 2" in problem


def test_a_list_shorter_than_its_count_is_reported():
    problem = count_problem(["one rule"], 2, "NOT_YET_ENFORCED", "NOT_YET_ENFORCED_COUNT")

    assert problem is not None
    assert "lower the count to 1" in problem


def test_a_list_exactly_as_long_as_its_count_reports_nothing():
    assert count_problem(["one rule", "another rule"], 2, "NOT_YET_ENFORCED", "NOT_YET_ENFORCED_COUNT") is None


def _shipped_module_row(stated_in: str) -> EnforcedRule:
    return EnforcedRule(
        rule="A finalize refusal.",
        stated_in=stated_in,
        enforcer="studio/run_phase.py::_validate_artifacts",
        proof="studio/tests/test_run_phase.py::test_finalize_requires_required_artifacts",
    )


def test_a_shipped_refusal_citing_a_doc_installed_repositories_lack_is_reported():
    problems = unshipped_stated_in_problems([_shipped_module_row("studio/docs/API.md")])

    assert len(problems) == 1
    assert problems[0].startswith(
        "'A finalize refusal.': studio/run_phase.py::_validate_artifacts runs in installed "
        "repositories, which have no studio/docs/API.md."
    )


@pytest.mark.parametrize(
    "stated_in", ["CLAUDE.md", ".claude/commands/run-phase.md", "studio/packs/game/ASSET_PIPELINE.md"]
)
def test_a_shipped_refusal_citing_claude_md_or_a_shipped_command_reports_nothing(stated_in):
    assert unshipped_stated_in_problems([_shipped_module_row(stated_in)]) == []


def test_a_command_file_studio_does_not_install_is_reported():
    problems = unshipped_stated_in_problems([_shipped_module_row(".claude/commands/not-shipped.md")])

    assert len(problems) == 1


def test_a_refusal_that_lives_only_in_studios_own_tests_may_cite_any_doc():
    row = _shipped_module_row("studio/docs/API.md")._replace(
        enforcer="studio/tests/test_spec_verification.py::_violations"
    )

    assert unshipped_stated_in_problems([row]) == []


def _proof_row(root: Path, rule: str, proof_source: str, proof_name: str) -> EnforcedRule:
    _write(root, f"tests/proof_{proof_name}.py", proof_source)
    return EnforcedRule(
        rule=rule,
        stated_in="docs/rules.md",
        enforcer="code/enforcer.py::refuse_bad_input",
        proof=f"tests/proof_{proof_name}.py::{proof_name}",
    )


def test_a_proof_lacking_see_is_counted_and_a_compliant_proof_is_not(tmp_path):
    lacking_see = _proof_row(
        tmp_path,
        "Lacks See.",
        "def test_lacks_see():\n    assert lines == ['  Fix: do the other thing']\n",
        "test_lacks_see",
    )
    lacking_fix = _proof_row(
        tmp_path,
        "Lacks Fix.",
        "def test_lacks_fix():\n    assert lines == ['  See docs/rules.md']\n",
        "test_lacks_fix",
    )
    compliant = _proof_row(
        tmp_path,
        "Compliant.",
        "def test_compliant():\n    assert lines == ['  Fix: do the other thing', '  See docs/rules.md']\n",
        "test_compliant",
    )

    lacking = rows_whose_proof_lacks_fix_and_see([lacking_see, lacking_fix, compliant], tmp_path)

    assert lacking == ["Lacks See.", "Lacks Fix."]
    assert count_problem(lacking, 2, "Planted", "PLANTED_COUNT") is None
    assert "Planted has 2 entries but PLANTED_COUNT is 1." in count_problem(lacking, 1, "Planted", "PLANTED_COUNT")


def test_see_naming_a_different_file_than_the_rows_stated_in_is_counted(tmp_path):
    row = _proof_row(
        tmp_path,
        "Points elsewhere.",
        "def test_points_elsewhere():\n    assert lines == ['  Fix: do it', '  See docs/other.md']\n",
        "test_points_elsewhere",
    )

    assert rows_whose_proof_lacks_fix_and_see([row], tmp_path) == ["Points elsewhere."]


def test_only_the_proofs_own_source_is_read_not_the_rest_of_its_file(tmp_path):
    row = _proof_row(
        tmp_path,
        "Neighbour holds it.",
        "def test_neighbour():\n    assert lines == ['  Fix: do it', '  See docs/rules.md']\n\n\n"
        "def test_bare():\n    assert lines\n",
        "test_neighbour",
    )._replace(proof="tests/proof_test_neighbour.py::test_bare")

    assert rows_whose_proof_lacks_fix_and_see([row], tmp_path) == ["Neighbour holds it."]


def test_a_class_proof_is_read_whole(tmp_path):
    row = _proof_row(
        tmp_path,
        "A class proof.",
        "class TestRefusal:\n"
        "    def test_fix(self):\n        assert lines[0] == '  Fix: do it'\n\n"
        "    def test_see(self):\n        assert lines[1] == '  See docs/rules.md'\n",
        "TestRefusal",
    )

    assert rows_whose_proof_lacks_fix_and_see([row], tmp_path) == []


def test_a_proofs_decorators_are_read_with_it(tmp_path):
    row = _proof_row(
        tmp_path,
        "A parametrized proof.",
        "import pytest\n\n\n"
        "@pytest.mark.parametrize('expected', [['  Fix: do it', '  See docs/rules.md']])\n"
        "def test_parametrized(expected):\n    assert lines == expected\n",
        "test_parametrized",
    )

    assert rows_whose_proof_lacks_fix_and_see([row], tmp_path) == []


def test_a_proof_that_is_not_there_is_counted(tmp_path):
    row = _proof_row(tmp_path, "Missing proof.", "def test_other():\n    pass\n", "test_other")
    row = row._replace(proof="tests/proof_test_other.py::test_gone")

    assert rows_whose_proof_lacks_fix_and_see([row], tmp_path) == ["Missing proof."]


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


# Counting reads only a row's results field, so these rows need no files on disk.
_UNMEASURED_ROW = JudgedRule(
    rule="The work is judged.",
    stated_in="docs/rules.md",
    judge="prompts/judge.py::judge_prompt",
)


def test_more_unmeasured_judges_than_the_count_is_reported():
    rows = [_UNMEASURED_ROW, _UNMEASURED_ROW._replace(rule="Another rule.")]

    problem = unmeasured_count_problem(rows, expected_count=1)

    assert problem is not None
    assert "JUDGED has 2 rows with no results but JUDGED_WITHOUT_MEASUREMENT_COUNT is 1" in problem


def test_fewer_unmeasured_judges_than_the_count_is_reported():
    problem = unmeasured_count_problem([_UNMEASURED_ROW], expected_count=2)

    assert problem is not None
    assert "lower the count to 1" in problem


def test_a_measured_judge_is_not_counted_as_unmeasured():
    measured_row = _UNMEASURED_ROW._replace(rule="A measured rule.", results="results/judge.md")

    assert unmeasured_count_problem([_UNMEASURED_ROW, measured_row], expected_count=1) is None


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


_PLANTED_LISTS = {
    "ENFORCED": ["Bad input is refused."],
    "NOT_YET_ENFORCED": ["Something nothing refuses yet."],
    "JUDGED": ["The work is judged."],
}

_SOUND_MEMORY_SORT_ROWS = (
    "| Bad input is refused. | listed | 1 | ENFORCED |\n"
    "| Something nothing refuses yet. | proxy | 2 | NOT_YET_ENFORCED |\n"
    "| The work is judged. | judge | 1 | JUDGED |\n"
    "| Only a person can tell. | person | 1 | this appendix |\n"
)

_SOUND_MEMORY_SORT_TOTALS = (
    "Totals: 1 listed, 0 by design, 2 proxy, 1 judge, 1 person, 1 fact, 1 personal; 7 in all."
)


def _memory_sort_spec(rows: str = _SOUND_MEMORY_SORT_ROWS, totals: str = _SOUND_MEMORY_SORT_TOTALS) -> str:
    return (
        "# A spec\n\n## Build Plan\n\nUnits.\n\n"
        f"{MEMORY_SORT_HEADING}\n\n{totals}\n\n"
        "| Rule | Label | Memories | Goes to |\n|---|---|---|---|\n"
        f"{rows}"
    )


def test_a_sound_memory_sort_reports_nothing():
    assert memory_sort_problems(_memory_sort_spec(), _PLANTED_LISTS) == []


def test_a_checkable_row_its_list_does_not_hold_is_reported():
    rows = _SOUND_MEMORY_SORT_ROWS + "| A rule nobody listed. | by design | 1 | NOT_YET_ENFORCED |\n"
    totals = _SOUND_MEMORY_SORT_TOTALS.replace("0 by design", "1 by design").replace("7 in all", "8 in all")

    problems = memory_sort_problems(_memory_sort_spec(rows, totals), _PLANTED_LISTS)

    assert problems == [
        "'A rule nobody listed.' goes to NOT_YET_ENFORCED, but NOT_YET_ENFORCED does not hold that sentence."
    ]


def test_a_checkable_row_whose_rule_was_promoted_to_enforced_reports_nothing():
    promoted = {
        "ENFORCED": _PLANTED_LISTS["ENFORCED"] + ["Something nothing refuses yet."],
        "NOT_YET_ENFORCED": [],
        "JUDGED": _PLANTED_LISTS["JUDGED"],
    }

    assert memory_sort_problems(_memory_sort_spec(), promoted) == []


def test_a_judge_row_sent_anywhere_but_judged_is_reported():
    rows = _SOUND_MEMORY_SORT_ROWS.replace("| judge | 1 | JUDGED |", "| judge | 1 | this appendix |")

    problems = memory_sort_problems(_memory_sort_spec(rows), _PLANTED_LISTS)

    assert problems == ["'The work is judged.' is labelled judge, so it goes to JUDGED, not this appendix."]


def test_a_person_row_put_in_a_list_is_reported():
    rows = _SOUND_MEMORY_SORT_ROWS.replace(
        "| Only a person can tell. | person | 1 | this appendix |",
        "| Something nothing refuses yet. | person | 1 | NOT_YET_ENFORCED |",
    )

    problems = memory_sort_problems(_memory_sort_spec(rows), _PLANTED_LISTS)

    assert problems == ["'Something nothing refuses yet.' is for a person, so it stays out of NOT_YET_ENFORCED."]


def test_a_listed_row_that_names_no_list_is_reported():
    rows = _SOUND_MEMORY_SORT_ROWS.replace("| listed | 1 | ENFORCED |", "| listed | 1 | this appendix |")

    problems = memory_sort_problems(_memory_sort_spec(rows), _PLANTED_LISTS)

    assert problems == ["'Bad input is refused.' is labelled listed, but this appendix is not one of the lists."]


def test_a_label_outside_the_five_is_reported():
    rows = _SOUND_MEMORY_SORT_ROWS.replace("| person | 1 | this appendix |", "| personal | 1 | this appendix |")

    problems = memory_sort_problems(_memory_sort_spec(rows), _PLANTED_LISTS)

    assert problems[0] == "'Only a person can tell.': 'personal' is not one of listed, by design, proxy, judge, person."


def test_totals_that_do_not_add_up_to_the_stated_total_are_reported():
    totals = _SOUND_MEMORY_SORT_TOTALS.replace("7 in all", "36 in all")

    problems = memory_sort_problems(_memory_sort_spec(totals=totals), _PLANTED_LISTS)

    assert problems == ["The totals add up to 7, not the 36 they state."]


def test_rows_standing_for_more_memories_than_their_label_total_are_reported():
    totals = _SOUND_MEMORY_SORT_TOTALS.replace("2 proxy", "1 proxy").replace("1 fact", "2 fact")

    problems = memory_sort_problems(_memory_sort_spec(totals=totals), _PLANTED_LISTS)

    assert problems == ["The proxy rows stand for 2 memories, but the totals say 1."]


def test_totals_missing_a_category_are_reported():
    totals = "Totals: 1 listed, 0 by design, 2 proxy, 1 judge, 1 person, 2 fact; 7 in all."

    problems = memory_sort_problems(_memory_sort_spec(totals=totals), _PLANTED_LISTS)

    assert problems == [
        "The totals name listed, by design, proxy, judge, person, fact; they should name "
        "listed, by design, proxy, judge, person, fact, personal, in that order."
    ]


def test_a_memory_sort_with_no_totals_line_is_reported():
    problems = memory_sort_problems(_memory_sort_spec(totals="Seven memories in all."), _PLANTED_LISTS)

    assert problems == ["The memory sort has no line reading 'Totals: <n> <label>, ...; <n> in all.'"]


def test_a_memory_file_named_in_the_sort_is_reported():
    rows = _SOUND_MEMORY_SORT_ROWS.replace("this appendix", "feedback_example.md")

    problems = memory_sort_problems(_memory_sort_spec(rows), _PLANTED_LISTS)

    assert problems == ["The memory sort names a memory file. State the rule, not where it came from."]


def test_a_spec_without_the_memory_sort_is_reported():
    problems = memory_sort_problems("# A spec\n\n## Build Plan\n", _PLANTED_LISTS)

    assert problems == ["The spec has no '## Appendix A: the memory sort' section."]

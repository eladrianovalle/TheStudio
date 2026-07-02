# Detest: Audit Tests Against AI-TDD Methodology

Audit the current repo's test suite against the Studio's AI-TDD methodology, find violations, and fix them. Like `/unstale` but specifically for tests.

## Arguments

- `$ARGUMENTS`: Optional. Scope hint like `--focus unit` or `--focus integration` or a specific path (e.g., `tests/test_checkout.py`). Default: all tests.

## Instructions

You are performing a methodology audit of this project's test suite. The goal: every test in this repo should follow AI-TDD principles: scenario-first structure, correct assertions, no self-mocking, no tautologies, no green-checkmark traps. You are not adding coverage. You are fixing the tests that already exist.

### Phase 1: Baseline

Run the project's test suite to capture a baseline pass/fail/skip count before changing anything. Detect the runner from config files (`pyproject.toml`, `package.json`, `build.gradle`, `go.mod`, etc.). If `$ARGUMENTS` specifies a path or focus, narrow scope accordingly.

### Phase 2: Parallel Audit

Launch **three** agents in parallel. Each agent audits a different category and returns a list of findings (file, line range, what's wrong). Agents must **not edit files**. Research only.

#### Agent 1: Anti-Pattern Detection

Scan every test file for AI-TDD anti-patterns:

- **Self-mocking tests:** mocking the class/module under test, then asserting the mock returns what it was told to return. The test would pass with the implementation deleted.
- **Tautological assertions:** `assertTrue(True)`, `assertEqual(mock.return_value, mock.return_value)`, asserting a mock returns exactly what it was configured to return with no real logic in between.
- **Hallucinated assertions:** `verify(mock).wasNotCalled()` or `assert not mock.called` when the code path clearly should invoke that dependency. Assertions that contradict the source code.
- **Testing implementation, not behavior:** tests that reference private methods, internal variable names, or implementation details that could change without changing behavior. Tests that break if you rename a private helper.
- **Green checkmark traps:** tests where deleting the implementation (replacing the function body with `pass` or `return None`) would still produce a green test run.

For each finding, note: file, line range, and which anti-pattern.

#### Agent 2: Structure & Stack Compliance

Check test files for structural violations:

- **Mixed frameworks:** JUnit 4 + JUnit 5 annotations in the same file, pytest functions mixed with `unittest.TestCase` subclasses in the same file, mixing assertion libraries inconsistently.
- **Missing scenario structure:** test functions that jump straight to code without any Given-When-Then structure (either in comments, docstrings, or naming). Not every test needs formal GWT, but complex tests with setup-action-assert phases should have them.
- **Missing parameterized tests:** pure functions (validators, formatters, calculators, parsers) being tested with copy-pasted individual test cases when parameterized tests would be clearer and more thorough.
- **Missing edge cases:** boundary conditions that are obvious from the function signature (empty input, None/null, zero, negative, max values) but have no corresponding test case.
- **Orphaned test utilities:** test helpers, fixtures, or factories that are defined but never used.

#### Agent 3: Coverage Quality

Check for tests that don't pull their weight:

- **Critical paths with no tests:** error handling, authentication checks, data validation, financial calculations, or state transitions that have zero test coverage. Flag gaps but do not write new tests.
- **Over-mocked tests:** tests where so many dependencies are mocked that the test is really just testing mock wiring. If a test mocks 5+ things and the function under test is 10 lines, the test is probably over-mocked.
- **Mutation verification candidates:** critical assertions guarding important business logic that should be spot-checked with mutation testing. Flag the 5-10 most important assertions across the whole suite; Phase 4 will use these for spot checks.

### Phase 3: Fix

Aggregate all findings from the three agents. For each finding:

1. **Verify it:** confirm the finding is real by reading the source code the test is supposed to cover. The source code is ground truth; if a test contradicts the code, the test is wrong.
2. **Classify it**:
   - **Auto-fix:** tautological assertions, missing GWT comments, framework mixing, parameterizable tests. Fix these directly.
   - **Flag for approval:** deleting tests entirely, major rewrites that change what's being asserted, anything where the test semantics change significantly. Describe the problem and proposed fix, then ask before proceeding.
   - **Skip:** false positives, cosmetic issues, tests where the "violation" is actually the right call for that specific case.
3. **Fix it:** rewrite bad tests following AI-TDD methodology:
   - Apply scenario-first structure (Given-When-Then) where missing on complex tests
   - Replace tautological assertions with real ones that test behavior
   - Remove self-mocking; test through the public API instead
   - Convert copy-pasted test cases to parameterized tests where appropriate
   - Use whatever frameworks the project already uses; do not introduce new dependencies

### Phase 4: Verify

After all fixes:

1. **Run the test suite:** execute the full test suite (or scoped subset if `$ARGUMENTS` narrowed it) to confirm all fixes pass.
2. **Spot mutation check:** pick 2-3 of the most critical assertions you fixed or flagged. Deliberately break the production code they guard (change `+` to `-`, flip a condition, return early). Run the relevant tests. If they still pass, the fix didn't work, so redo it. Revert the mutations after checking.
3. **Summarize** what was fixed, grouped by category:
   - **Anti-patterns eliminated** (self-mocking, tautologies, hallucinated assertions)
   - **Structure improved** (GWT added, parameterized, framework mixing resolved)
   - **Coverage quality improved** (over-mocking reduced, meaningful assertions added)
   - **Flagged for user** (tests that need human judgment, critical gaps found but not filled)
   - **Mutation check results** (which assertions were spot-checked and whether they caught the introduced bug)

### Key Rules

- **Don't rewrite tests for style:** only fix methodology violations. If a test is ugly but correct and meaningful, leave it.
- **The source code is ground truth:** if a test contradicts the implementation, the test is wrong. Read the source before deciding a test is correct.
- **Don't touch non-test code:** the production code is not yours to change (except temporarily for mutation checks, then revert immediately).

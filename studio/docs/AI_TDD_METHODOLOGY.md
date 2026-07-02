# AI-Assisted Test-Driven Development (AI-TDD) Methodology

This document codifies how we use AI assistants for test generation and validation. It exists because **AI is excellent at brainstorming and boilerplate but dangerous at assertions**, and our workflow must enforce that boundary.

---

## The Core Problem

When you ask an AI to "write tests," it optimizes for green checkmarks, not correctness. It will:
- Mock the system under test itself (testing nothing)
- Write tautological assertions (`assertTrue(true)`)
- Use deprecated frameworks or mix incompatible ones
- Verify that mocks *weren't* called when they clearly should be
- Produce 100% coverage of 0% of your actual logic

**The fix is structural, not prompting harder.** Our workflow separates the things AI is good at from the things it will silently get wrong.

---

## The Paradigm: AI as Scenario Generator, Not SDET

| AI's Job | Human's Job |
|----------|-------------|
| Brainstorm edge cases and scenarios | Decide which scenarios matter |
| Generate Given-When-Then specs | Review and approve the spec list |
| Write mock setup and boilerplate | Write or strictly review assertions |
| Generate parameterized test data | Validate data correctness |
| Format and structure test files | Verify tests actually catch bugs |

**You are the SDET. The AI is your brainstorming assistant and boilerplate typist.**

---

## Three Rules for AI-Assisted Testing

### Rule 1: Scenario-First (Given-When-Then Brainstorm)

**Never ask AI to write test code first.** Ask it to generate scenarios in plain English.

Bad:
> "Write tests for this checkout function."

Good:
> "Read this CheckoutUseCase. List all test scenarios using Given-When-Then format. Pay special attention to edge cases, null values, concurrency failures, and boundary conditions. Do not write any code yet."

Once you review the scenario list, selectively approve which ones to implement:
> "Write test code for scenarios 3, 5, and 8."

This prevents the AI from deciding what matters. That's your job.

### Rule 2: Context Boundary (Define the Stack)

Testing frameworks are fragmented. If you don't specify, AI will mix JUnit 4 and 5, Mockito and MockK, pytest and unittest in the same file.

**Every test generation request must open with a stack declaration:**

> "We are using [framework]. We DO NOT use [banned framework]. Write the setup block and initialize mocks for dependencies. Do not write test cases yet."

By constraining the AI to setup-only, you get the tedious boilerplate done without risking assertion integrity.

### Rule 3: Parameterized Data Typist

For pure functions (formatters, validators, calculators), AI excels at generating exhaustive data tables:

> "Here is a function that calculates shipping costs based on weight, region, and loyalty tier. Generate a CSV-formatted table of 20 diverse test cases including extreme edge cases, invalid inputs, and boundary values."

You write the single parameterized test function. AI provides the data.

---

## Anti-Patterns to Catch and Kill

### The Hallucinated Assertion
AI writes `verify(mock).wasNotCalled()` when the logic clearly should call that dependency. **Always manually review assert/verify blocks.**

### The Self-Mocking Test
AI mocks the class under test, then asserts the mock returns what it was told to return. This tests the mocking framework, not your code. **If the test would pass even with the implementation deleted, it's worthless.**

### Testing Implementation, Not Behavior
If renaming a private variable breaks the test, it's testing internals. **Tests must target the public API and observable behavior.**

### The Green Checkmark Trap
All tests pass, coverage looks great, nothing is actually validated. **Mutation test: deliberately introduce a bug (change + to -). If the test still passes, the test is broken.**

---

## The Mutation Verification Rule

Every AI-generated test suite MUST pass this check before acceptance:

1. Pick 2-3 critical assertions
2. Deliberately break the production code they should guard
3. Run the tests
4. If tests still pass → the AI wrote bad tests → reject and redo

This is non-negotiable. A test that doesn't catch a known bug is worse than no test: it creates false confidence.

---

## Workflow Integration

This methodology applies everywhere AI generates or reviews test code in our Studio workflow:

- **Tech phase implementations** must follow scenario-first test specification
- **QA role advocates** must demand AI-TDD compliance in test strategies
- **QA role contrarians** must verify tests aren't self-mocking or tautological
- **Engineering contrarians** must challenge test quality, not just coverage numbers
- **Code validators** should flag common anti-patterns (mock-of-SUT, assertTrue(true))

See `TEST_DRIVEN_GUIDE.md` for the full tech phase TDD workflow.
See the `test_engineer` and `qa` role focuses in `studio.manifest.json` for role-specific enforcement.

---

## Summary

| Principle | One-liner |
|-----------|-----------|
| Scenarios before code | AI lists what to test; you decide what matters |
| Stack boundary | Declare frameworks explicitly; ban what you don't use |
| Data, not assertions | AI generates test data; you own the assertions |
| Mutation verification | Break the code; if tests still pass, tests are broken |
| Behavior over implementation | Test public API, not private internals |

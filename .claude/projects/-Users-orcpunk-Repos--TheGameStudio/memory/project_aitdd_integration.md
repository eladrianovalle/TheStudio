---
name: AI-TDD Integration Initiative
description: Integrating AI-assisted TDD methodology into Studio workflow — new test_engineer role, enforcement at validation and instruction generation layers
type: project
---

AI-TDD methodology is being baked into the Studio workflow as a first-class concern. Core principles: scenario-first (Given-When-Then before code), stack boundary declarations, human-owned assertions, mutation verification, anti-pattern detection (self-mocking, tautological assertions, green checkmark trap).

**Why:** AI-generated tests that mock the SUT or write tautological assertions create dangerous false confidence. The existing QA role focuses on release ops, not test methodology integrity.

**How to apply:** A new `test_engineer` role is proposed (not in studio_core by default — opt-in via `+test_engineer` or `studio_tech` role pack). The methodology doc lives at `studio/docs/AI_TDD_METHODOLOGY.md`. Changes touch the manifest, role prompts, slash commands, validators, and instruction generation. Engineering and QA contrarians get sharpened with AI-TDD awareness too.

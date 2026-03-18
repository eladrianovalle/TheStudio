#!/usr/bin/env python3
"""
Question-surfacing mode for Studio runs.

Pure function library — no side effects, no state, no I/O.
Generates instruction templates that switch advocate/contrarian output
from deliverable production to structured question surfacing.
"""
from __future__ import annotations

import textwrap
from typing import Dict, List, Tuple


QUESTION_MODE_HEADER = "<!-- output_type: questions -->"


def is_question_mode(mode_str: str | None) -> bool:
    """Return True if mode_str indicates question-surfacing mode."""
    if mode_str is None:
        return False
    return mode_str.strip().lower() == "questions"


def generate_question_instructions(role_data: Dict) -> Tuple[str, str]:
    """Generate advocate and contrarian instruction text for question mode.

    Args:
        role_data: Dict with keys: title, advocate_focus, contrarian_focus,
                   deliverables (list of str), and optionally escalate_on.

    Returns:
        (advocate_instructions, contrarian_instructions) tuple of strings.
    """
    title = role_data.get("title", "Role")
    advocate_focus = role_data.get("advocate_focus", "")
    contrarian_focus = role_data.get("contrarian_focus", "")
    deliverables = role_data.get("deliverables", [])
    deliverables_str = "\n".join(f"  - {d}" for d in deliverables)

    advocate = textwrap.dedent(f"""\
        {QUESTION_MODE_HEADER}

        # Question-Surfacing Mode — {title} (Advocate)

        **Your role:** Surface the open questions that must be answered before
        this role can produce its standard deliverables.

        **Normal deliverables (for reference — do NOT produce these now):**
        {deliverables_str}

        **Advocate focus:** {advocate_focus}

        ## Instructions

        Produce a numbered list of **5–15 questions**, each tagged with a
        priority level:

        - **[P0]** — Blocking: cannot start work without an answer.
        - **[P1]** — Important: answer shapes the approach significantly.
        - **[P2]** — Nice-to-know: refines quality but work can begin without it.

        ## Anti-generic guardrails

        - Do NOT ask questions that are answerable from the input text.
        - Each question MUST name the specific decision it would unblock
          (e.g., "Answering this determines whether we need server-side state").
        - Prefer questions that expose hidden assumptions over questions that
          request missing data.
        - Do NOT produce deliverables, specs, or recommendations — only questions.

        ## Output format

        ```
        ## Open Questions — {title}

        1. [P0] <question text>
           *Unblocks:* <what decision this enables>

        2. [P1] <question text>
           *Unblocks:* <what decision this enables>
        ...
        ```
    """)

    contrarian = textwrap.dedent(f"""\
        {QUESTION_MODE_HEADER}

        # Question-Surfacing Mode — {title} (Contrarian)

        **Your role:** Challenge the advocate's question list. Are these the
        *right* questions? Are any missing? Are priorities correct?

        **Contrarian focus:** {contrarian_focus}

        ## Instructions

        1. Review each question the advocate surfaced.
        2. Challenge at least **30%** of the questions as wrong-level priority
           (e.g., a P2 that should be P0, or a P0 that is already answerable).
        3. Surface at least **2 unstated assumptions** the advocate's questions
           reveal but do not explicitly name.
        4. Identify at least **2 missing questions** the advocate failed to ask.
        5. Remove any duplicate or overly generic questions.

        ## Output format

        ```
        ## Question Challenges — {title}

        ### Priority Corrections
        - Q3: Advocate tagged [P1], should be [P0] because ...
        - Q7: Advocate tagged [P0], should be [P2] because ...

        ### Unstated Assumptions
        - The advocate assumes ... but this has not been established.
        - The advocate assumes ... which may not hold if ...

        ### Missing Questions
        - [P0] <question the advocate missed>
        - [P1] <question the advocate missed>

        ### Revised Question Set
        <Consolidated, deduplicated, re-prioritised question list>
        ```
    """)

    return advocate, contrarian


def generate_question_integrator_instructions() -> str:
    """Generate integrator instructions for question mode.

    The integrator consolidates questions across roles into a single
    prioritised set — it does NOT produce a roadmap or plan.
    """
    return textwrap.dedent("""\
        # Question-Mode Integrator

        You are consolidating questions from all participating roles into a
        single, deduplicated, prioritised question set.

        ## Instructions

        1. **Deduplicate** — merge questions that ask the same thing in
           different words. Keep the most precise wording.
        2. **Group by theme** — organise questions by topic (e.g., "Audience",
           "Technical Constraints", "Scope") rather than by role.
        3. **Resolve priority conflicts** — if two roles assigned different
           priorities to the same question, use the higher priority and note
           the disagreement.
        4. **Surface cross-role dependencies** — flag questions where the
           answer from one discipline constrains another.
        5. **Do NOT produce a roadmap, plan, or recommendations.** The output
           is a question document, not a decision document.

        ## Output format

        ```
        ## Consolidated Questions

        ### <Theme 1>
        1. [P0] <question> (from: Design, Engineering)
           *Unblocks:* ...

        ### <Theme 2>
        2. [P1] <question> (from: Product)
           *Unblocks:* ...

        ...

        ## Summary
        - Total questions: N
        - P0 (blocking): N
        - P1 (important): N
        - P2 (nice-to-know): N
        - Top 3 highest-leverage questions: Q1, Q5, Q9
        ```
    """)

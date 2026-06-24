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
        this role can produce its standard deliverables. This is a pre-flight
        reconnaissance pass — "what don't we know yet?" — that produces
        decision points for the team to resolve before a full run.

        **Normal deliverables (for reference — do NOT produce these now):**
        {deliverables_str}

        **Advocate focus:** {advocate_focus}

        ## Instructions

        Produce **5–15 decision points**, each tagged with a priority level:

        - **P0 (Blocking):** Cannot start work without an answer.
        - **P1 (Important):** Answer shapes the approach significantly.
        - **P2 (Nice-to-know):** Refines quality but work can begin without it.

        ## Anti-generic guardrails

        - Do NOT ask questions that are answerable from the input text.
        - Each question MUST name the specific decision it would unblock
          (e.g., "Answering this determines whether we need server-side state").
        - Prefer questions that expose hidden assumptions over questions that
          request missing data.
        - Do NOT surface questions that assume complexity. Phrase questions to
          test whether the simple approach works before asking about the complex
          one (e.g., GOOD: "Can a single database handle expected load?"
          BAD: "Which sharding strategy should we use?").
        - Each question must target a single decision. Compound questions
          ("Should we do X and if so how should we handle Y?") must be split.
        - Do NOT produce deliverables, specs, or recommendations — only questions.

        ## Output format

        Use the standard decision point blockquote format:

        ```
        ## Open Questions — {title}

        > **DECISION [P0]:** <question text>
        > **Unblocks:** <what decision this enables>

        > **DECISION [P1]:** <question text>
        > **Unblocks:** <what decision this enables>

        > **DECISION [P2]:** <question text>
        > **Unblocks:** <what decision this enables>
        ```

        Each decision point MUST use the `> **DECISION [Pn]:**` blockquote
        format. Do NOT use numbered lists or bullet points for questions.
    """)

    contrarian = textwrap.dedent(f"""\
        {QUESTION_MODE_HEADER}

        # Question-Surfacing Mode — {title} (Contrarian)

        **Your role:** Challenge the advocate's decision points. Are these the
        *right* questions? Are any missing? Are priorities correct?

        **Contrarian focus:** {contrarian_focus}

        ## Instructions

        1. Review each decision point the advocate surfaced.
        2. Challenge at least **30%** of the decision points as wrong-level
           priority (e.g., a P2 that should be P0, or a P0 that is already
           answerable).
        3. Surface at least **2 unstated assumptions** the advocate's questions
           reveal but do not explicitly name.
        4. Identify at least **2 missing decision points** the advocate failed
           to surface.
        5. Remove duplicate or overly generic questions. Judge each remaining
           question on *relevance* — does answering it move us toward the best,
           simplest system? Do NOT drop a genuinely-open question just to keep
           the list short. At this stage, missing a real question is worse than
           carrying one extra; the bias toward cutting belongs in the
           deliverable phases, not in deciding what to ask.

        ## Output format

        ```
        ## Question Challenges — {title}

        ### Priority Corrections
        - Advocate's "Should we ..." tagged [P1], should be [P0] because ...
        - Advocate's "What is ..." tagged [P0], should be [P2] because ...

        ### Unstated Assumptions
        - The advocate assumes ... but this has not been established.
        - The advocate assumes ... which may not hold if ...

        ### Missing Decision Points

        > **DECISION [P0]:** <question the advocate missed>
        > **Unblocks:** <what this enables>

        > **DECISION [P1]:** <question the advocate missed>
        > **Unblocks:** <what this enables>

        ### Revised Decision Set
        <Consolidated, deduplicated, re-prioritised set using the blockquote
        DECISION format above>
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

        You are consolidating decision points from all participating roles into
        a single, deduplicated, prioritised decision set. This produces the
        `decisions.md` content — a pre-flight checklist of what must be resolved
        before a full deliverable run.

        ## Instructions

        1. **Deduplicate** — merge decision points that ask the same thing in
           different words. Keep the most precise wording.
        2. **Group by theme** — organise decisions by topic (e.g., "Audience",
           "Technical Constraints", "Scope") rather than by role.
        3. **Resolve priority conflicts** — if two roles assigned different
           priorities to the same question, use the higher priority and note
           the disagreement.
        4. **Surface cross-role dependencies** — flag questions where the
           answer from one discipline constrains another.
        5. **Do NOT produce a roadmap, plan, or recommendations.** The output
           is a decision point document, not a plan.

        ## Output format

        Use the standard decision point blockquote format throughout:

        ```
        ## Consolidated Decision Points

        ### <Theme 1>

        > **DECISION [P0]:** <question> (from: Design, Engineering)
        > **Unblocks:** ...

        ### <Theme 2>

        > **DECISION [P1]:** <question> (from: Product)
        > **Unblocks:** ...

        ...

        ## Summary
        - Total decision points: N
        - P0 (blocking): N
        - P1 (important): N
        - P2 (nice-to-know): N
        - Top 3 highest-leverage decisions: ...
        ```
    """)

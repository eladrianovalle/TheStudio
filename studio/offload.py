"""
CLAUDE.md offload analyzer.

Classifies sections, detects embedded constraints, scores pointer strength,
generates reports, and evaluates validation protocol results.

Pure function library with no side effects except explicit I/O functions
(create_backup, restore_backup, and the file-scan helpers scan_existing_docs,
scan_slash_commands, detect_cross_repo_context).
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

# --- Constants ---


_IDENTITY_PATTERNS = re.compile(
    r"What This Is|Convention|Important", re.IGNORECASE
)

# Tier constants
TIER_ALWAYS_INLINE = "always-inline"
TIER_TRIGGER_OFFLOADABLE = "trigger-offloadable"
TIER_REFERENCE_OFFLOADABLE = "reference-offloadable"

# Rating constants
RATING_STRONG = "strong"
RATING_MEDIUM = "medium"
RATING_WEAK = "weak"

_IMPERATIVE_RE = re.compile(
    r"(?:^|[—.,]\s*)"          # start of line or after clause boundary
    r"(?:(?:you|it|they|we)\s+)?"  # optional subject
    r"(must|never|always|required)\b",
    re.MULTILINE | re.IGNORECASE,
)

# "the required" / "a required": adjective usage, not imperative
_ADJECTIVE_REQUIRED_RE = re.compile(
    r"\b(?:the|a)\s+required\b", re.IGNORECASE
)

_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")

_BULLET_MODULE_RE = re.compile(r"^\s*-\s+\*\*`", re.MULTILINE)

_TABLE_ROW_RE = re.compile(r"^\|.+\|$", re.MULTILINE)

_IMPERATIVE_VERB_RE = re.compile(
    r"\b(read|check|review|consult|see)\b.*(?:/|\.md)", re.IGNORECASE
)

_TRIGGER_RE = re.compile(
    r"\b(when|before|if)\b.*\b(?:\w+ing|need|want|start|begin)\b", re.IGNORECASE
)

_FILE_PATH_RE = re.compile(r"(?:/[\w./-]+|[\w./-]+\.md)")

_CONSEQUENCE_RE = re.compile(
    r"\b(to avoid|required for|necessary for|otherwise|failure to|may cause)\b", re.IGNORECASE
)

_WORD_RE = re.compile(r"\w+")
_SLUG_RE = re.compile(r"[^\w]+")


# --- Pure Functions ---


def classify_sections(content: str) -> list[dict]:
    """Parse CLAUDE.md content into sections and classify each by tier.

    Splits on ``## `` headers.  Each section is classified as one of:
    ``always-inline``, ``reference-offloadable``, or ``trigger-offloadable``.

    Args:
        content: Full text of CLAUDE.md.

    Returns:
        List of dicts with keys: name, start_line, end_line, content,
        tier, reason.
    """
    lines = content.split("\n")
    sections: list[dict] = []

    # Find section boundaries
    boundaries: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if line.startswith("## "):
            boundaries.append((i, line[3:].strip()))

    if not boundaries:
        # Whole file is one section
        return [{
            "name": "(preamble)",
            "start_line": 1,
            "end_line": len(lines),
            "content": content,
            "tier": TIER_ALWAYS_INLINE,
            "reason": "Single section / preamble",
        }]

    # Add preamble if content exists before first header
    if boundaries[0][0] > 0:
        preamble_lines = lines[:boundaries[0][0]]
        preamble_text = "\n".join(preamble_lines)
        if preamble_text.strip():
            sections.append({
                "name": "(preamble)",
                "start_line": 1,
                "end_line": boundaries[0][0],
                "content": preamble_text,
                "tier": TIER_ALWAYS_INLINE,
                "reason": "Preamble / identity content",
            })

    for idx, (line_num, name) in enumerate(boundaries):
        if idx + 1 < len(boundaries):
            end_line = boundaries[idx + 1][0]
        else:
            end_line = len(lines)

        section_lines = lines[line_num:end_line]
        section_content = "\n".join(section_lines)
        body_count = sum(1 for ln in section_lines[1:] if ln.strip())

        tier, reason = _classify_single_section(
            name, section_content, body_count
        )
        sections.append({
            "name": name,
            "start_line": line_num + 1,  # 1-indexed
            "end_line": end_line,
            "content": section_content,
            "tier": tier,
            "reason": reason,
        })

    return sections


def _classify_single_section(
    name: str, content: str, body_line_count: int
) -> tuple[str, str]:
    """Classify a single section into a tier.

    Returns:
        (tier, reason) tuple.
    """
    # Identity patterns
    if _IDENTITY_PATTERNS.search(name):
        return TIER_ALWAYS_INLINE, f"Identity pattern in header: {name!r}"

    # Short section with imperative constraints
    if body_line_count <= 5 and _IMPERATIVE_RE.search(content):
        return TIER_ALWAYS_INLINE, "Short section with imperative constraints"

    # Reference-offloadable: code blocks with 5+ commands
    code_blocks = _CODE_BLOCK_RE.findall(content)
    for block in code_blocks:
        command_lines = [
            ln for ln in block.split("\n")
            if ln.strip()
            and not ln.strip().startswith("```")
            and not ln.strip().startswith("#")
        ]
        if len(command_lines) >= 5:
            return (
                TIER_REFERENCE_OFFLOADABLE,
                f"Code block with {len(command_lines)} commands",
            )

    # Reference-offloadable: module/file catalog (4+ bullet points)
    module_bullets = _BULLET_MODULE_RE.findall(content)
    if len(module_bullets) >= 4:
        return (
            TIER_REFERENCE_OFFLOADABLE,
            f"Module catalog with {len(module_bullets)} entries",
        )

    # Reference-offloadable: tables with 4+ rows
    table_rows = _TABLE_ROW_RE.findall(content)
    # Subtract header + separator rows (first two matches per table)
    data_rows = max(0, len(table_rows) - 2)
    if data_rows >= 4:
        return (
            TIER_REFERENCE_OFFLOADABLE,
            f"Table with {data_rows} data rows",
        )

    # Trigger-offloadable: anything else that's long enough
    if body_line_count > 10:
        return TIER_TRIGGER_OFFLOADABLE, f"General section ({body_line_count} lines)"

    # Default: inline
    return TIER_ALWAYS_INLINE, f"Short section ({body_line_count} lines)"


def detect_embedded_constraints(sections: list[dict]) -> list[dict]:
    """Scan offloadable sections for imperative constraints.

    Only processes sections classified as ``trigger-offloadable`` or
    ``reference-offloadable``.

    Args:
        sections: Output of :func:`classify_sections`.

    Returns:
        List of dicts with keys: section, line, text, constraint_type.
    """
    constraints: list[dict] = []

    for section in sections:
        if section["tier"] == TIER_ALWAYS_INLINE:
            continue

        section_lines = section["content"].split("\n")
        base_line = section["start_line"]

        for i, line_text in enumerate(section_lines):
            if not line_text.strip():
                continue

            # Skip lines that are adjective usage of "required"
            cleaned = line_text
            if _ADJECTIVE_REQUIRED_RE.search(cleaned):
                # Remove adjective usages before checking
                cleaned = _ADJECTIVE_REQUIRED_RE.sub("", cleaned)

            match = _IMPERATIVE_RE.search(cleaned)
            if match:
                word = (match.group(1) or match.group(2)).lower()
                constraints.append({
                    "section": section["name"],
                    "line": base_line + i,
                    "text": line_text.strip(),
                    "constraint_type": word,
                })

    return constraints


def score_pointer_strength(pointer_text: str) -> dict:
    """Score a pointer stub's strength on a 0.0-1.0 scale.

    Checks for imperative verbs, trigger conditions, file paths,
    and consequence language.

    Args:
        pointer_text: The proposed pointer/stub text.

    Returns:
        Dict with keys: score, has_imperative, has_trigger, has_path,
        has_consequence, rating.
    """
    has_imperative = bool(_IMPERATIVE_VERB_RE.search(pointer_text))
    has_trigger = bool(_TRIGGER_RE.search(pointer_text))
    has_path = bool(_FILE_PATH_RE.search(pointer_text))
    has_consequence = bool(_CONSEQUENCE_RE.search(pointer_text))

    score = 0.0
    if has_imperative:
        score += 0.3
    if has_trigger:
        score += 0.4
    if has_path:
        score += 0.2
    if has_consequence:
        score += 0.1

    if score >= 0.7:
        rating = RATING_STRONG
    elif score >= 0.5:
        rating = RATING_MEDIUM
    else:
        rating = RATING_WEAK

    return {
        "score": score,
        "has_imperative": has_imperative,
        "has_trigger": has_trigger,
        "has_path": has_path,
        "has_consequence": has_consequence,
        "rating": rating,
    }


def generate_pointer_stub(section: dict, companion_path: str) -> dict:
    """Generate a pointer stub for an offloadable section.

    Produces a STRONG pattern pointer: imperative + trigger + file path
    + consequence.

    Args:
        section: A single section dict from :func:`classify_sections`.
        companion_path: Path to the companion doc that will hold the
            offloaded content.

    Returns:
        Dict with keys: inline_stub, manifest_entry, strength.
    """
    name = section["name"]

    # Build trigger condition based on tier
    if section["tier"] == TIER_REFERENCE_OFFLOADABLE:
        trigger = f"When you need {name.lower()} details"
    else:
        trigger = f"Before working on {name.lower()}"

    inline_stub = (
        f"**{name}:** {trigger}, read `{companion_path}` "
        f"for the full reference — required for correct implementation."
    )

    manifest_entry = {
        "trigger": trigger,
        "path": companion_path,
        "description": f"Full {name.lower()} reference (offloaded from CLAUDE.md)",
    }

    strength = score_pointer_strength(inline_stub)

    return {
        "inline_stub": inline_stub,
        "manifest_entry": manifest_entry,
        "strength": strength,
    }


def generate_canary_token(slug: str) -> str:
    """Generate a canary token for offload validation.

    Format: ``CANARY-{slug}-{hex8}`` where hex8 is 8 random hex chars.

    Args:
        slug: Identifier slug for the section.

    Returns:
        Canary token string.
    """
    hex8 = secrets.token_hex(4)
    return f"CANARY-{slug}-{hex8}"


def verify_canary_isolation(
    claude_md_content: str, tokens: list[str]
) -> list[str]:
    """Check that no canary tokens leaked into CLAUDE.md content.

    Args:
        claude_md_content: Full text of CLAUDE.md.
        tokens: List of canary tokens to check.

    Returns:
        List of tokens that were found (leaked). Empty list means pass.
    """
    leaked: list[str] = []
    for token in tokens:
        if token in claude_md_content:
            leaked.append(token)
    return leaked


def evaluate_protocol_run(results: list[dict]) -> dict:
    """Evaluate validation protocol results from n>=20 sessions.

    Each result must have keys: ``session_id``, ``pointer_pattern``,
    ``echo_found``, ``token_matched``.

    Pass criteria:
        - ``total_sessions >= 20``
        - ``echo_rate >= 0.8``
        - No pre-exemptions (every session counts)

    Args:
        results: List of per-session validation results.

    Returns:
        Dict with keys: passed, total_sessions, echo_rate, per_pattern,
        failures.
    """
    total = len(results)
    if total == 0:
        return {
            "passed": False,
            "total_sessions": 0,
            "echo_rate": 0.0,
            "per_pattern": {},
            "failures": ["No sessions provided"],
        }

    echo_count = sum(1 for r in results if r.get("echo_found", False))
    echo_rate = echo_count / total

    # Per-pattern breakdown
    pattern_hits: dict[str, list[bool]] = {}
    for r in results:
        pattern = r.get("pointer_pattern", "unknown")
        if pattern not in pattern_hits:
            pattern_hits[pattern] = []
        pattern_hits[pattern].append(r.get("echo_found", False))

    per_pattern: dict[str, float] = {}
    for pattern, hits in pattern_hits.items():
        per_pattern[pattern] = sum(hits) / len(hits) if hits else 0.0

    failures: list[str] = []
    if total < 20:
        failures.append(
            f"Insufficient sessions: {total} < 20 required"
        )
    if echo_rate < 0.8:
        failures.append(
            f"Echo rate too low: {echo_rate:.2f} < 0.80 required"
        )

    passed = len(failures) == 0

    return {
        "passed": passed,
        "total_sessions": total,
        "echo_rate": echo_rate,
        "per_pattern": per_pattern,
        "failures": failures,
    }


def reconcile_with_existing(
    sections: list[dict], existing_docs: list[dict]
) -> list[dict]:
    """Match offloadable sections against existing companion docs.

    For each offloadable section, checks if an existing doc covers
    similar content via heading-level matching and path references.

    Args:
        sections: Output of :func:`classify_sections` (offloadable only
            will be filtered internally).
        existing_docs: Output of :func:`scan_existing_docs`.

    Returns:
        List of dicts with keys: section, action, target, reason.
    """
    recommendations: list[dict] = []

    offloadable = [
        s for s in sections if s["tier"] != TIER_ALWAYS_INLINE
    ]

    # Precompute heading word-sets per doc
    doc_heading_words: list[list[set]] = []
    for doc in existing_docs:
        doc_heading_words.append([
            set(_WORD_RE.findall(h.lower())) for h in doc["headings"]
        ])

    for section in offloadable:
        name_lower = section["name"].lower()
        name_words = set(_WORD_RE.findall(name_lower))

        best_match: dict | None = None
        best_overlap = 0

        for doc_idx, doc in enumerate(existing_docs):
            for heading_words in doc_heading_words[doc_idx]:
                overlap = len(name_words & heading_words)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = doc

            # Check if section content references this doc path
            if doc["path"] in section["content"]:
                best_match = doc
                best_overlap = max(best_overlap, len(name_words))
                break

        if best_match and best_overlap >= 2:
            recommendations.append({
                "section": section["name"],
                "action": "merge",
                "target": best_match["path"],
                "reason": (
                    f"Existing doc covers similar content "
                    f"({best_overlap} keyword overlap)"
                ),
            })
        else:
            slug = _SLUG_RE.sub("_", name_lower).strip("_")
            recommendations.append({
                "section": section["name"],
                "action": "create",
                "target": f"studio/docs/{slug}.md",
                "reason": "No existing doc covers this content",
            })

    return recommendations


# --- I/O Functions ---


def detect_cross_repo_context() -> dict:
    """Detect whether we are in the Studio repo or a consumer project.

    Checks in order: ``$STUDIO_ROOT`` env var, ``.studio/source/`` dir,
    ``.studio/`` dir, ``CLAUDE.md`` existence.

    Returns:
        Dict with keys: is_studio_repo, companion_root, detection_method.
    """
    # Check STUDIO_ROOT env var
    studio_root = os.environ.get("STUDIO_ROOT")
    if studio_root:
        root = Path(studio_root)
        return {
            "is_studio_repo": (root / "studio" / "run_phase.py").exists(),
            "companion_root": str(root),
            "detection_method": "STUDIO_ROOT env var",
        }

    cwd = Path.cwd()

    # Check .studio/source/ (cross-repo install)
    if (cwd / ".studio" / "source").is_dir():
        return {
            "is_studio_repo": False,
            "companion_root": str(cwd / ".studio"),
            "detection_method": ".studio/source/ directory",
        }

    # Check .studio/ dir
    if (cwd / ".studio").is_dir():
        return {
            "is_studio_repo": (cwd / "studio" / "run_phase.py").exists(),
            "companion_root": str(cwd / ".studio"),
            "detection_method": ".studio/ directory",
        }

    # Check CLAUDE.md exists at cwd
    if (cwd / "CLAUDE.md").exists():
        is_studio = (cwd / "studio" / "run_phase.py").exists()
        companion = str(cwd / "studio" / "docs") if is_studio else str(cwd)
        return {
            "is_studio_repo": is_studio,
            "companion_root": companion,
            "detection_method": "CLAUDE.md in cwd",
        }

    return {
        "is_studio_repo": False,
        "companion_root": str(cwd),
        "detection_method": "fallback (cwd)",
    }


def scan_existing_docs(companion_root: str) -> list[dict]:
    """List existing .md files that could serve as merge targets.

    Args:
        companion_root: Root directory to scan for docs.

    Returns:
        List of dicts with keys: path, headings, line_count.
    """
    root = Path(companion_root)
    results: list[dict] = []

    if not root.is_dir():
        return results

    for md_file in sorted(root.rglob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        lines = text.split("\n")
        headings = [
            ln.lstrip("#").strip()
            for ln in lines
            if ln.startswith("#")
        ]

        results.append({
            "path": str(md_file),
            "headings": headings,
            "line_count": len(lines),
        })

    return results


def scan_slash_commands(
    commands_dir: str, offloaded_sections: list[dict]
) -> list[dict]:
    """Check slash commands for references to content being offloaded.

    Args:
        commands_dir: Path to ``.claude/commands/`` directory.
        offloaded_sections: Sections being offloaded (from
            :func:`classify_sections`, filtered to offloadable tiers).

    Returns:
        List of dicts with keys: command, references, risk.
    """
    cmd_dir = Path(commands_dir)
    conflicts: list[dict] = []

    if not cmd_dir.is_dir():
        return conflicts

    for cmd_file in sorted(cmd_dir.glob("*.md")):
        try:
            text = cmd_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        text_lower = text.lower()
        references: list[str] = []

        for section in offloaded_sections:
            name_lower = section["name"].lower()
            if name_lower in text_lower:
                references.append(section["name"])

        if references:
            risk = "high" if len(references) >= 3 else "medium"
            conflicts.append({
                "command": cmd_file.name,
                "references": references,
                "risk": risk,
            })

    return conflicts


def create_backup(files: list[str], backup_dir: str) -> str:
    """Copy files to a timestamped backup directory.

    Args:
        files: List of file paths to back up.
        backup_dir: Base directory for backups.

    Returns:
        Path to the created backup directory.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = Path(backup_dir) / f"backup_{ts}"
    dest.mkdir(parents=True, exist_ok=True)

    for file_path in files:
        src = Path(file_path)
        if src.exists():
            shutil.copy2(str(src), str(dest / src.name))

    return str(dest)


def restore_backup(backup_path: str) -> list[str]:
    """Restore files from a backup directory.

    Copies each file in the backup back to its original location
    by matching filenames in the current working directory tree.

    Args:
        backup_path: Path to the backup directory created by
            :func:`create_backup`.

    Returns:
        List of restored file paths.
    """
    backup = Path(backup_path)
    if not backup.is_dir():
        return []

    restored: list[str] = []
    cwd = Path.cwd()

    for backed_up in sorted(backup.iterdir()):
        if not backed_up.is_file():
            continue

        target = cwd / backed_up.name
        shutil.copy2(str(backed_up), str(target))
        restored.append(str(target))

    return restored


def generate_report(
    sections: list[dict],
    constraints: list[dict],
    pointers: list[dict],
    canaries: dict,
    reconciliation: list[dict],
) -> str:
    """Generate the full classification report as formatted markdown.

    This is the only analysis function that produces formatted output.
    All inputs are pure data structures from the other functions.

    Args:
        sections: Output of :func:`classify_sections`.
        constraints: Output of :func:`detect_embedded_constraints`.
        pointers: List of pointer stub dicts from
            :func:`generate_pointer_stub`.
        canaries: Dict mapping section slug to canary token.
        reconciliation: Output of :func:`reconcile_with_existing`.

    Returns:
        Formatted markdown report string.
    """
    lines: list[str] = []

    # --- Summary stats ---
    total_lines = sum(
        s["end_line"] - s["start_line"] + 1 for s in sections
    )
    inline_lines = sum(
        s["end_line"] - s["start_line"] + 1
        for s in sections if s["tier"] == TIER_ALWAYS_INLINE
    )
    offloaded_lines = total_lines - inline_lines
    reduction = (offloaded_lines / total_lines * 100) if total_lines else 0.0

    lines.append("# CLAUDE.md Offload Analysis Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Current lines:** {total_lines}")
    lines.append(f"- **Projected inline lines:** {inline_lines}")
    lines.append(f"- **Offloadable lines:** {offloaded_lines}")
    lines.append(f"- **Reduction:** {reduction:.0f}%")
    lines.append("")

    # --- Section classification table ---
    lines.append("## Section Classification")
    lines.append("")
    lines.append("| Section | Lines | Tier | Reason |")
    lines.append("|---------|-------|------|--------|")
    for s in sections:
        line_count = s["end_line"] - s["start_line"] + 1
        lines.append(
            f"| {s['name']} | {line_count} | {s['tier']} | {s['reason']} |"
        )
    lines.append("")

    # --- Pointer stubs preview ---
    if pointers:
        lines.append("## Pointer Stubs Preview")
        lines.append("")
        for p in pointers:
            strength = p.get("strength", {})
            rating = strength.get("rating", "unknown")
            lines.append(f"**[{rating}]** {p['inline_stub']}")
            lines.append("")
        lines.append("")

    # --- Manifest table ---
    if pointers:
        lines.append("## Manifest Entries")
        lines.append("")
        lines.append("| Trigger | Path | Description |")
        lines.append("|---------|------|-------------|")
        for p in pointers:
            entry = p.get("manifest_entry", {})
            lines.append(
                f"| {entry.get('trigger', '')} "
                f"| {entry.get('path', '')} "
                f"| {entry.get('description', '')} |"
            )
        lines.append("")

    # --- Embedded constraints ---
    if constraints:
        lines.append("## Embedded Constraints Flagged")
        lines.append("")
        lines.append(
            "The following imperative constraints were found in "
            "offloadable sections. These MUST be preserved inline or "
            "in the pointer stub."
        )
        lines.append("")
        for c in constraints:
            lines.append(
                f"- **L{c['line']}** [{c['constraint_type']}] "
                f"in *{c['section']}*: {c['text']}"
            )
        lines.append("")

    # --- Reconciliation ---
    if reconciliation:
        lines.append("## Reconciliation Recommendations")
        lines.append("")
        lines.append("| Section | Action | Target | Reason |")
        lines.append("|---------|--------|--------|--------|")
        for r in reconciliation:
            lines.append(
                f"| {r['section']} | {r['action']} "
                f"| {r['target']} | {r['reason']} |"
            )
        lines.append("")

    # --- Canary tokens ---
    if canaries:
        lines.append("## Canary Tokens")
        lines.append("")
        for slug, token in canaries.items():
            lines.append(f"- `{slug}`: `{token}`")
        lines.append("")

    # --- Validation status ---
    lines.append("## VALIDATION STATUS: PRE-RELEASE")
    lines.append("")
    lines.append(
        "This offload plan has NOT been validated with the echo protocol. "
        "Run 20+ validation sessions before applying changes."
    )
    lines.append("")

    return "\n".join(lines)

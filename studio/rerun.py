#!/usr/bin/env python3
"""
Rerun mode detection and failure context injection for Studio runs.

Enables Studio to feed previous rejection reasons back into the next advocate
prompt, improving convergence speed by addressing specific concerns from
previous iterations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class RejectionContext:
    """Context extracted from a previous rejection."""
    iteration: int
    role: str | None  # None for non-studio phases
    reasons: List[str]
    full_text: str
    
    def format_for_prompt(self) -> str:
        """Format rejection context for inclusion in advocate prompt."""
        if not self.reasons:
            return ""
        
        lines = ["**Previous iteration was REJECTED for the following reasons:**", ""]
        for i, reason in enumerate(self.reasons, 1):
            lines.append(f"{i}. {reason}")
        lines.append("")
        lines.append("Please address these concerns in your revised proposal.")
        return "\n".join(lines)


def detect_rerun_mode(run_dir: Path) -> bool:
    """
    Detect if this is a rerun by checking for existing contrarian files.
    
    Args:
        run_dir: Path to the Studio run directory
        
    Returns:
        True if previous contrarian files exist, False otherwise
    """
    if not run_dir.exists():
        return False
    
    # Check for any contrarian files
    contrarian_files = list(run_dir.glob("contrarian*.md"))
    return len(contrarian_files) > 0


def find_latest_rejection(run_dir: Path, role: str | None = None) -> Path | None:
    """
    Find the most recent contrarian file containing a REJECTED verdict.
    
    Args:
        run_dir: Path to the Studio run directory
        role: Optional role name for studio phase (e.g., "product", "engineering")
        
    Returns:
        Path to the latest rejection file, or None if no rejections found
    """
    if not run_dir.exists():
        return None
    
    # Build pattern based on role
    if role:
        pattern = f"contrarian--{role}--*.md"
    else:
        pattern = "contrarian_*.md"
    
    contrarian_files = sorted(run_dir.glob(pattern), reverse=True)
    
    for file_path in contrarian_files:
        content = file_path.read_text(encoding="utf-8")
        if "VERDICT: REJECTED" in content:
            return file_path
    
    return None


def extract_rejection_reasons(contrarian_content: str) -> List[str]:
    """
    Extract structured rejection reasons from contrarian response.
    
    Looks for common patterns:
    - Numbered lists after "REJECTED"
    - Sections like "## Critical Issues" or "## Reasons"
    - Bullet points with concerns
    - Paragraph-based concerns
    
    Args:
        contrarian_content: Full text of contrarian response
        
    Returns:
        List of extracted rejection reasons
    """
    reasons: List[str] = []
    
    # Check for rejection
    if "REJECTED" not in contrarian_content.upper():
        return reasons
    
    # Strategy 1: Look for sections with issues/reasons/concerns
    section_patterns = [
        r'##\s*(?:Critical\s+)?Issues?\s*\n\n.+?\n\n(.+?)(?=\n##|$)',
        r'##\s*(?:Rejection\s+)?Reasons?\s*\n\n.+?\n\n(.+?)(?=\n##|$)',
        r'##\s*Concerns?\s*\n\n.+?\n\n(.+?)(?=\n##|$)',
    ]
    
    section_content = None
    for pattern in section_patterns:
        match = re.search(pattern, contrarian_content, re.DOTALL | re.IGNORECASE)
        if match:
            section_content = match.group(1)
            break
    
    # If no section found, use content after VERDICT: REJECTED
    if not section_content:
        verdict_match = re.search(
            r'VERDICT:\s*REJECTED.*?(?=\n##|$)',
            contrarian_content,
            re.DOTALL | re.IGNORECASE
        )
        section_content = verdict_match.group(0) if verdict_match else contrarian_content
    
    # Pattern 1: Numbered lists with bold titles and descriptions
    # Format: "1. **Title** - description"
    numbered_bold_pattern = r'^\s*\d+\.\s*\*\*(.+?)\*\*\s*-\s*(.+?)(?=\n\d+\.|\n\n|$)'
    numbered_matches = list(re.finditer(numbered_bold_pattern, section_content, re.MULTILINE | re.DOTALL))
    
    if numbered_matches:
        for match in numbered_matches:
            title = match.group(1).strip()
            description = match.group(2).strip()
            reason = f"{title} - {description}"
            reasons.append(reason)
    
    # Pattern 2: Simple numbered lists (1. reason)
    if not reasons:
        simple_numbered_pattern = r'^\s*\d+\.\s*(.+?)(?=\n\d+\.|\n\n|$)'
        simple_matches = re.finditer(simple_numbered_pattern, section_content, re.MULTILINE | re.DOTALL)
        for match in simple_matches:
            reason = match.group(1).strip()
            # Clean markdown
            reason = re.sub(r'\*\*(.+?)\*\*', r'\1', reason)
            reason = re.sub(r'\*(.+?)\*', r'\1', reason)
            reason = reason.strip()
            if reason and len(reason) > 10:
                reasons.append(reason)
    
    # Pattern 3: Bullet points (- reason, * reason)
    if not reasons:
        bullet_pattern = r'^\s*[-*]\s*(.+?)(?=\n\s*[-*]|\n\n|$)'
        bullet_matches = re.finditer(bullet_pattern, section_content, re.MULTILINE)
        for match in bullet_matches:
            reason = match.group(1).strip()
            if reason and len(reason) > 10:
                reasons.append(reason)
    
    # Pattern 4: "Reasons:" section
    if not reasons:
        reasons_match = re.search(
            r'(?:Reasons?|Concerns?|Issues?):\s*\n(.+?)(?=\n##|\n\*\*|$)',
            section_content,
            re.DOTALL | re.IGNORECASE
        )
        if reasons_match:
            reasons_text = reasons_match.group(1)
            # Split on newlines and clean
            for line in reasons_text.split('\n'):
                line = line.strip().lstrip('-*•').strip()
                if line and len(line) > 10:
                    reasons.append(line)
    
    # Pattern 5: Paragraph extraction (fallback)
    if not reasons:
        # Split into paragraphs and take first few substantive ones
        paragraphs = [p.strip() for p in section_content.split('\n\n') if p.strip()]
        for para in paragraphs[:3]:  # Limit to first 3 paragraphs
            # Skip the verdict line itself
            if 'VERDICT:' in para.upper():
                continue
            if len(para) > 20 and not para.startswith('#'):
                reasons.append(para)
    
    # Clean up reasons
    cleaned_reasons = []
    for reason in reasons:
        # Remove markdown formatting
        reason = re.sub(r'\*\*(.+?)\*\*', r'\1', reason)  # Bold
        reason = re.sub(r'\*(.+?)\*', r'\1', reason)      # Italic
        reason = re.sub(r'`(.+?)`', r'\1', reason)        # Code
        reason = reason.strip()
        
        # Skip very short or empty reasons
        if len(reason) > 15:
            cleaned_reasons.append(reason)
    
    return cleaned_reasons[:5]  # Limit to top 5 reasons


def load_rejection_context(run_dir: Path, role: str | None = None) -> RejectionContext | None:
    """
    Load rejection context from the most recent rejected contrarian response.
    
    Args:
        run_dir: Path to the Studio run directory
        role: Optional role name for studio phase
        
    Returns:
        RejectionContext if a rejection is found, None otherwise
    """
    rejection_file = find_latest_rejection(run_dir, role)
    if not rejection_file:
        return None
    
    content = rejection_file.read_text(encoding="utf-8")
    reasons = extract_rejection_reasons(content)
    
    # Extract iteration number from filename
    # Format: contrarian_2.md or contrarian--product--02.md
    filename = rejection_file.stem
    iteration_match = re.search(r'(\d+)', filename)
    iteration = int(iteration_match.group(1)) if iteration_match else 0
    
    return RejectionContext(
        iteration=iteration,
        role=role,
        reasons=reasons,
        full_text=content
    )


def inject_context_into_prompt(base_prompt: str, context: RejectionContext | None) -> str:
    """
    Inject rejection context into advocate prompt.
    
    Args:
        base_prompt: Original advocate prompt template
        context: Rejection context to inject, or None
        
    Returns:
        Modified prompt with context injected
    """
    if not context or not context.reasons:
        return base_prompt
    
    # Find a good injection point (before deliverables/checklist if present)
    injection_markers = [
        "## Deliverables",
        "## Your Task",
        "## Requirements",
        "---",
    ]
    
    injection_point = len(base_prompt)
    for marker in injection_markers:
        pos = base_prompt.find(marker)
        if pos != -1:
            injection_point = min(injection_point, pos)
    
    # Build context section
    context_section = [
        "",
        "---",
        "",
        context.format_for_prompt(),
        "",
        "---",
        "",
    ]
    
    # Insert context
    modified_prompt = (
        base_prompt[:injection_point] +
        "\n".join(context_section) +
        base_prompt[injection_point:]
    )
    
    return modified_prompt


def generate_rerun_instructions(run_dir: Path, role: str | None = None) -> str:
    """
    Generate instructions for a rerun with failure context.
    
    Args:
        run_dir: Path to the Studio run directory
        role: Optional role name for studio phase
        
    Returns:
        Markdown-formatted instructions for the rerun
    """
    context = load_rejection_context(run_dir, role)
    
    if not context:
        return "No previous rejections found. Starting fresh iteration."
    
    lines = [
        "# Rerun Mode Detected",
        "",
        f"Previous iteration {context.iteration} was **REJECTED**.",
        "",
    ]
    
    if context.role:
        lines.append(f"**Role**: {context.role}")
        lines.append("")
    
    lines.extend([
        "## Rejection Reasons",
        "",
    ])
    
    for i, reason in enumerate(context.reasons, 1):
        lines.append(f"{i}. {reason}")
    
    lines.extend([
        "",
        "## Next Steps",
        "",
        "1. Review the rejection reasons above",
        "2. Address each concern in your revised proposal",
        "3. The advocate prompt will automatically include this context",
        "4. Focus on the specific issues raised rather than starting from scratch",
        "",
    ])
    
    return "\n".join(lines)

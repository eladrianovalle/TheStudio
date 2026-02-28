#!/usr/bin/env python3
"""
Document validation for Studio discussion phase outputs.

Validates advocate/contrarian documents for completeness, consistency,
and proper structure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set


@dataclass
class ValidationResult:
    """Result of a validation check."""
    passed: bool
    issues: List[str]
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    @property
    def has_issues(self) -> bool:
        """Check if there are any issues (failures or warnings)."""
        return len(self.issues) > 0 or len(self.warnings) > 0


class DocumentValidator:
    """Validator for Studio discussion phase documents."""
    
    # File size limit for validation (1MB)
    MAX_FILE_SIZE = 1_000_000  # 1MB in bytes
    
    def check_completeness(self, doc_path: Path, required_sections: List[str]) -> ValidationResult:
        """
        Check if document contains all required sections.
        
        Args:
            doc_path: Path to document file
            required_sections: List of required section headers (without # prefix)
            
        Returns:
            ValidationResult with missing sections as issues
        """
        if not doc_path.exists():
            return ValidationResult(
                passed=False,
                issues=[f"Document not found: {doc_path}"]
            )
        
        # Check file size before reading
        file_size = doc_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            return ValidationResult(
                passed=False,
                issues=[
                    f"File too large for validation: {file_size:,} bytes (limit: {self.MAX_FILE_SIZE:,} bytes)",
                    f"Large files may cause performance issues. Consider splitting into smaller documents."
                ]
            )
        
        content = doc_path.read_text(encoding="utf-8")
        
        # Extract all section headers (## Header or # Header)
        section_pattern = r'^#{1,3}\s+(.+?)$'
        found_sections = set()
        for match in re.finditer(section_pattern, content, re.MULTILINE):
            section_title = match.group(1).strip()
            found_sections.add(section_title.lower())
        
        # Check for missing sections
        missing = []
        for required in required_sections:
            required_lower = required.lower()
            # Check exact match or partial match
            if not any(required_lower in found or found in required_lower 
                      for found in found_sections):
                missing.append(required)
        
        return ValidationResult(
            passed=len(missing) == 0,
            issues=missing
        )
    
    def check_consistency(self, advocate_path: Path, contrarian_path: Path) -> ValidationResult:
        """
        Check if contrarian addresses advocate's key points.
        
        Args:
            advocate_path: Path to advocate document
            contrarian_path: Path to contrarian document
            
        Returns:
            ValidationResult with unaddressed points as warnings
        """
        if not advocate_path.exists():
            return ValidationResult(
                passed=False,
                issues=[f"Advocate document not found: {advocate_path}"]
            )
        
        if not contrarian_path.exists():
            return ValidationResult(
                passed=False,
                issues=[f"Contrarian document not found: {contrarian_path}"]
            )
        
        # Check file sizes
        advocate_size = advocate_path.stat().st_size
        contrarian_size = contrarian_path.stat().st_size
        if advocate_size > self.MAX_FILE_SIZE or contrarian_size > self.MAX_FILE_SIZE:
            return ValidationResult(
                passed=False,
                issues=[f"One or more files too large for validation (limit: {self.MAX_FILE_SIZE:,} bytes)"]
            )
        
        advocate_content = advocate_path.read_text(encoding="utf-8")
        contrarian_content = contrarian_path.read_text(encoding="utf-8")
        
        # Extract key points from advocate (numbered lists, bullet points, bold text)
        advocate_points = self._extract_key_points(advocate_content)
        
        # Check which points are addressed in contrarian
        unaddressed = []
        for point in advocate_points:
            if not self._is_addressed(point, contrarian_content):
                unaddressed.append(point)
        
        # Use warnings instead of hard failures for consistency
        # (contrarian might address points implicitly)
        return ValidationResult(
            passed=True,  # Don't fail on consistency issues
            issues=[],
            warnings=unaddressed if len(unaddressed) > 3 else []  # Only warn if >3 unaddressed
        )
    
    def check_format(self, doc_path: Path) -> ValidationResult:
        """
        Check document format and structure.
        
        Args:
            doc_path: Path to document file
            
        Returns:
            ValidationResult with format issues
        """
        if not doc_path.exists():
            return ValidationResult(
                passed=False,
                issues=[f"Document not found: {doc_path}"]
            )
        
        content = doc_path.read_text(encoding="utf-8")
        issues = []
        warnings = []
        
        # Check for title (# Header at start)
        if not re.match(r'^#\s+.+', content, re.MULTILINE):
            warnings.append("Missing top-level title (# Header)")
        
        # Check for excessive blank lines (>3 consecutive)
        if re.search(r'\n\n\n\n+', content):
            warnings.append("Excessive blank lines (>3 consecutive)")
        
        # Check for proper markdown list formatting
        # Look for common errors like missing space after bullet
        if re.search(r'^\d+\.[^\s]', content, re.MULTILINE):
            warnings.append("Numbered list items missing space after period")
        
        if re.search(r'^[-*][^\s]', content, re.MULTILINE):
            warnings.append("Bullet list items missing space after marker")
        
        # Check for very short documents (<100 chars)
        if len(content.strip()) < 100:
            issues.append("Document is too short (<100 characters)")
        
        return ValidationResult(
            passed=len(issues) == 0,
            issues=issues,
            warnings=warnings
        )
    
    def check_verdict(self, contrarian_path: Path) -> ValidationResult:
        """
        Check if contrarian document contains a valid verdict.
        
        Args:
            contrarian_path: Path to contrarian document
            
        Returns:
            ValidationResult indicating if verdict is present and valid
        """
        if not contrarian_path.exists():
            return ValidationResult(
                passed=False,
                issues=[f"Contrarian document not found: {contrarian_path}"]
            )
        
        content = contrarian_path.read_text(encoding="utf-8")
        
        # Check for VERDICT: APPROVED or VERDICT: REJECTED
        verdict_pattern = r'VERDICT:\s*(APPROVED|REJECTED)'
        match = re.search(verdict_pattern, content, re.IGNORECASE)
        
        if not match:
            return ValidationResult(
                passed=False,
                issues=["Missing or invalid verdict (must be 'VERDICT: APPROVED' or 'VERDICT: REJECTED')"]
            )
        
        verdict = match.group(1).upper()
        
        # If rejected, check for reasons
        if verdict == "REJECTED":
            # Look for numbered lists, bullet points, or reason sections after verdict
            verdict_pos = match.end()
            content_after_verdict = content[verdict_pos:]
            
            has_reasons = (
                re.search(r'^\s*\d+\.', content_after_verdict, re.MULTILINE) or
                re.search(r'^\s*[-*]', content_after_verdict, re.MULTILINE) or
                re.search(r'(?:Reasons?|Issues?|Concerns?):', content_after_verdict, re.IGNORECASE)
            )
            
            if not has_reasons:
                return ValidationResult(
                    passed=True,
                    issues=[],
                    warnings=["REJECTED verdict without clear rejection reasons"]
                )
        
        return ValidationResult(passed=True, issues=[])
    
    def _extract_key_points(self, content: str) -> List[str]:
        """Extract key points from document (numbered lists, bullets, bold text)."""
        points = []
        
        # Extract numbered list items
        numbered_pattern = r'^\s*\d+\.\s*(.+?)$'
        for match in re.finditer(numbered_pattern, content, re.MULTILINE):
            point = match.group(1).strip()
            if len(point) > 20:  # Only substantial points
                points.append(point[:100])  # Limit length
        
        # Extract bullet points
        bullet_pattern = r'^\s*[-*]\s*(.+?)$'
        for match in re.finditer(bullet_pattern, content, re.MULTILINE):
            point = match.group(1).strip()
            if len(point) > 20:
                points.append(point[:100])
        
        # Extract bold text (often used for key concepts)
        bold_pattern = r'\*\*(.+?)\*\*'
        for match in re.finditer(bold_pattern, content):
            point = match.group(1).strip()
            if len(point) > 10 and len(point) < 100:
                points.append(point)
        
        # Deduplicate and limit
        return list(dict.fromkeys(points))[:10]  # Top 10 unique points
    
    def _is_addressed(self, point: str, contrarian_content: str) -> bool:
        """Check if a point is addressed in contrarian content."""
        # Extract key words from point (ignore common words)
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'is', 'are', 'was', 'were'}
        
        # Clean and tokenize point
        point_clean = re.sub(r'[^\w\s]', ' ', point.lower())
        words = [w for w in point_clean.split() if w not in stop_words and len(w) > 3]
        
        # Check if at least 50% of key words appear in contrarian content
        if not words:
            return True  # Can't verify, assume addressed
        
        contrarian_lower = contrarian_content.lower()
        matches = sum(1 for word in words if word in contrarian_lower)
        
        return matches >= len(words) * 0.5
    
    def validate_run(self, run_dir: Path, phase: str, required_sections: dict = None) -> ValidationResult:
        """
        Validate all documents in a run directory.
        
        Args:
            run_dir: Path to run directory
            phase: Phase name (market, design, tech, studio)
            required_sections: Dict mapping role to required sections
            
        Returns:
            Combined ValidationResult for all documents
        """
        all_issues = []
        all_warnings = []
        
        if not run_dir.exists():
            return ValidationResult(
                passed=False,
                issues=[f"Run directory not found: {run_dir}"]
            )
        
        # Find advocate and contrarian files
        advocate_files = sorted(run_dir.glob("advocate*.md"))
        contrarian_files = sorted(run_dir.glob("contrarian*.md"))
        
        if not advocate_files:
            all_issues.append("No advocate documents found")
        
        if not contrarian_files:
            all_issues.append("No contrarian documents found")
        
        # Validate each advocate/contrarian pair
        for advocate_file in advocate_files:
            # Find corresponding contrarian file
            # Extract iteration number
            advocate_match = re.search(r'(\d+)', advocate_file.stem)
            if advocate_match:
                iteration = advocate_match.group(1)
                contrarian_pattern = f"contrarian*{iteration}.md"
                contrarian_matches = list(run_dir.glob(contrarian_pattern))
                
                if contrarian_matches:
                    contrarian_file = contrarian_matches[0]
                    
                    # Check format
                    format_result = self.check_format(advocate_file)
                    all_warnings.extend(format_result.warnings)
                    all_issues.extend(format_result.issues)
                    
                    format_result = self.check_format(contrarian_file)
                    all_warnings.extend(format_result.warnings)
                    all_issues.extend(format_result.issues)
                    
                    # Check verdict
                    verdict_result = self.check_verdict(contrarian_file)
                    all_issues.extend(verdict_result.issues)
                    all_warnings.extend(verdict_result.warnings)
                    
                    # Check consistency
                    consistency_result = self.check_consistency(advocate_file, contrarian_file)
                    all_issues.extend(consistency_result.issues)
                    all_warnings.extend(consistency_result.warnings)
        
        return ValidationResult(
            passed=len(all_issues) == 0,
            issues=all_issues,
            warnings=all_warnings
        )

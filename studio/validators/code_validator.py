#!/usr/bin/env python3
"""
Code validation for Studio implementation phase outputs.

Validates generated code using deterministic checks like pytest, mypy, ruff.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class CheckResult:
    """Result of a code check."""
    check_name: str
    passed: bool
    output: str
    duration_seconds: float = 0.0
    
    @property
    def summary(self) -> str:
        """Get one-line summary of check result."""
        status = "✓ PASSED" if self.passed else "✗ FAILED"
        return f"{status} - {self.check_name}"


class CodeValidator:
    """Validator for Studio implementation phase code."""
    
    def __init__(self, timeout: int = 60):
        """
        Initialize code validator.
        
        Args:
            timeout: Maximum seconds to wait for each check
        """
        self.timeout = timeout
    
    def run_check(self, command: List[str], cwd: Path = None) -> CheckResult:
        """
        Run a single code check command.
        
        Args:
            command: Command to run as list of strings
            cwd: Working directory for command
            
        Returns:
            CheckResult with command output and pass/fail status
        """
        import time
        
        check_name = command[0]
        start_time = time.time()
        
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            duration = time.time() - start_time
            
            return CheckResult(
                check_name=check_name,
                passed=result.returncode == 0,
                output=result.stdout + result.stderr,
                duration_seconds=duration
            )
        
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return CheckResult(
                check_name=check_name,
                passed=False,
                output=f"Command timed out after {self.timeout} seconds",
                duration_seconds=duration
            )
        
        except FileNotFoundError:
            return CheckResult(
                check_name=check_name,
                passed=False,
                output=f"Command not found: {check_name}. Is it installed?",
                duration_seconds=0.0
            )
        
        except Exception as e:
            return CheckResult(
                check_name=check_name,
                passed=False,
                output=f"Error running check: {e}",
                duration_seconds=0.0
            )
    
    def run_pytest(self, project_dir: Path, test_path: str = None) -> CheckResult:
        """
        Run pytest on project.
        
        Args:
            project_dir: Project root directory
            test_path: Optional specific test file/directory
            
        Returns:
            CheckResult for pytest
        """
        command = ["pytest", "-v"]
        if test_path:
            command.append(test_path)
        
        return self.run_check(command, cwd=project_dir)
    
    def run_mypy(self, project_dir: Path, target: str = ".") -> CheckResult:
        """
        Run mypy type checking.
        
        Args:
            project_dir: Project root directory
            target: Target file/directory to check
            
        Returns:
            CheckResult for mypy
        """
        command = ["mypy", target, "--strict"]
        return self.run_check(command, cwd=project_dir)
    
    def run_ruff(self, project_dir: Path, target: str = ".") -> CheckResult:
        """
        Run ruff linting.
        
        Args:
            project_dir: Project root directory
            target: Target file/directory to check
            
        Returns:
            CheckResult for ruff
        """
        command = ["ruff", "check", target]
        return self.run_check(command, cwd=project_dir)
    
    def run_black(self, project_dir: Path, target: str = ".", check_only: bool = True) -> CheckResult:
        """
        Run black code formatting check.
        
        Args:
            project_dir: Project root directory
            target: Target file/directory to check
            check_only: If True, only check formatting without modifying files
            
        Returns:
            CheckResult for black
        """
        command = ["black", target]
        if check_only:
            command.append("--check")
        
        return self.run_check(command, cwd=project_dir)
    
    def validate_implementation(self, project_dir: Path, checks: List[str] = None) -> List[CheckResult]:
        """
        Run all configured checks on implementation.
        
        Args:
            project_dir: Project root directory
            checks: List of check names to run (default: all)
            
        Returns:
            List of CheckResults
        """
        if checks is None:
            checks = ["pytest", "mypy", "ruff"]
        
        results = []
        
        for check in checks:
            if check == "pytest":
                results.append(self.run_pytest(project_dir))
            elif check == "mypy":
                results.append(self.run_mypy(project_dir))
            elif check == "ruff":
                results.append(self.run_ruff(project_dir))
            elif check == "black":
                results.append(self.run_black(project_dir))
            else:
                results.append(CheckResult(
                    check_name=check,
                    passed=False,
                    output=f"Unknown check: {check}"
                ))
        
        return results
    
    def format_results(self, results: List[CheckResult]) -> str:
        """
        Format check results as human-readable string.
        
        Args:
            results: List of CheckResults
            
        Returns:
            Formatted string with all results
        """
        lines = ["# Code Validation Results", ""]
        
        passed_count = sum(1 for r in results if r.passed)
        total_count = len(results)
        
        lines.append(f"**Summary**: {passed_count}/{total_count} checks passed")
        lines.append("")
        
        for result in results:
            lines.append(f"## {result.check_name}")
            lines.append("")
            lines.append(f"**Status**: {result.summary}")
            lines.append(f"**Duration**: {result.duration_seconds:.2f}s")
            lines.append("")
            
            if not result.passed:
                lines.append("**Output**:")
                lines.append("```")
                # Limit output to first 50 lines
                output_lines = result.output.split('\n')[:50]
                lines.extend(output_lines)
                if len(result.output.split('\n')) > 50:
                    lines.append("... (output truncated)")
                lines.append("```")
                lines.append("")
        
        return "\n".join(lines)

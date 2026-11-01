"""
Real Workspace Tools for Master Agent Execution.
Per Section 3:
Provides actual file editing, shell command execution, HTTP probing, and test runner tools
for the Master Agent autonomous loop.
"""

import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orchestration.security.command_policy import (
    CommandEvaluation,
    CommandSecurityPolicy,
    PolicyDecision,
)
from orchestration.security.sanitizer import sanitize_text


@dataclass
class ToolExecutionResult:
    tool_name: str
    success: bool
    output: Any
    error: Optional[str] = None
    duration_ms: float = 0.0


class WorkspaceTools:
    """
    Real tool registry callable by the Master Agent with active security boundaries.
    """

    def __init__(
        self,
        workspace_root: Path,
        security_policy: Optional[CommandSecurityPolicy] = None,
    ):
        self.workspace_root = workspace_root.resolve()
        if security_policy is None:
            from orchestration.config import OrchestrationConfig
            audit_log = OrchestrationConfig.load().audit_dir / "command_execution_audit.jsonl"
            security_policy = CommandSecurityPolicy(self.workspace_root, audit_log_path=audit_log)
        self.security_policy = security_policy

    def read_file(self, relative_path: str) -> ToolExecutionResult:
        t0 = time.perf_counter()
        target = (self.workspace_root / relative_path).resolve()
        try:
            content = target.read_text(encoding="utf-8")
            return ToolExecutionResult(
                tool_name="read_file",
                success=True,
                output=content,
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            return ToolExecutionResult(
                tool_name="read_file",
                success=False,
                output=None,
                error=str(e),
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

    def write_file(self, relative_path: str, content: str) -> ToolExecutionResult:
        t0 = time.perf_counter()
        target = (self.workspace_root / relative_path).resolve()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ToolExecutionResult(
                tool_name="write_file",
                success=True,
                output=f"Successfully wrote {len(content)} characters to {relative_path}",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            return ToolExecutionResult(
                tool_name="write_file",
                success=False,
                output=None,
                error=str(e),
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

    def patch_file(self, relative_path: str, target_content: str, replacement_content: str) -> ToolExecutionResult:
        t0 = time.perf_counter()
        target = (self.workspace_root / relative_path).resolve()
        try:
            if not target.exists():
                return ToolExecutionResult(
                    tool_name="patch_file",
                    success=False,
                    output=None,
                    error=f"File {relative_path} does not exist",
                    duration_ms=(time.perf_counter() - t0) * 1000,
                )

            current = target.read_text(encoding="utf-8")
            if target_content not in current:
                return ToolExecutionResult(
                    tool_name="patch_file",
                    success=False,
                    output=None,
                    error=f"Target content not found in {relative_path}",
                    duration_ms=(time.perf_counter() - t0) * 1000,
                )

            updated = current.replace(target_content, replacement_content, 1)
            target.write_text(updated, encoding="utf-8")
            return ToolExecutionResult(
                tool_name="patch_file",
                success=True,
                output=f"Successfully patched {relative_path}",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            return ToolExecutionResult(
                tool_name="patch_file",
                success=False,
                output=None,
                error=str(e),
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

    def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 60,
        confirmed: bool = False,
    ) -> ToolExecutionResult:
        """
        Executes shell command strictly within the security policy and workspace boundary.
        """
        t0 = time.perf_counter()

        # 1. Evaluate command policy
        evaluation: CommandEvaluation = self.security_policy.evaluate(command, cwd=cwd)

        # 2. Handle DENIED decisions
        if evaluation.decision == PolicyDecision.DENIED:
            self.security_policy.record_audit(
                requested_command=command,
                validated_command=None,
                policy_decision=evaluation.decision,
                result_status="DENIED",
                reason=evaluation.reason,
            )
            return ToolExecutionResult(
                tool_name="run_command",
                success=False,
                output=None,
                error=f"SECURITY DENIED: {evaluation.reason}",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        # 3. Handle REQUIRES_CONFIRMATION decisions
        if evaluation.decision == PolicyDecision.REQUIRES_CONFIRMATION and not confirmed:
            self.security_policy.record_audit(
                requested_command=command,
                validated_command=None,
                policy_decision=evaluation.decision,
                result_status="CONFIRMATION_REQUIRED",
                reason=evaluation.reason,
            )
            return ToolExecutionResult(
                tool_name="run_command",
                success=False,
                output=None,
                error=f"CONFIRMATION REQUIRED: {evaluation.reason}",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        # 4. Enforce workspace working directory boundary
        work_dir = (Path(cwd) if cwd else self.workspace_root).resolve()
        try:
            work_dir.relative_to(self.workspace_root)
        except ValueError:
            self.security_policy.record_audit(
                requested_command=command,
                validated_command=None,
                policy_decision=PolicyDecision.DENIED,
                result_status="DENIED",
                reason=f"Working directory '{work_dir}' outside workspace root.",
            )
            return ToolExecutionResult(
                tool_name="run_command",
                success=False,
                output=None,
                error=f"SECURITY DENIED: Working directory '{work_dir}' is outside workspace boundary.",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        # 5. Sanitize environment to prevent credential inheritance
        safe_env = self.security_policy.sanitize_environment()

        try:
            res = subprocess.run(
                evaluation.validated_command or command,
                shell=True,
                cwd=str(work_dir),
                env=safe_env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration_ms = (time.perf_counter() - t0) * 1000
            success = (res.returncode == 0)

            clean_stdout = sanitize_text(res.stdout)
            clean_stderr = sanitize_text(res.stderr)

            self.security_policy.record_audit(
                requested_command=command,
                validated_command=evaluation.validated_command or command,
                policy_decision=evaluation.decision,
                result_status="EXECUTED" if success else "FAILED",
                exit_code=res.returncode,
                reason=evaluation.reason,
            )

            return ToolExecutionResult(
                tool_name="run_command",
                success=success,
                output={
                    "stdout": clean_stdout,
                    "stderr": clean_stderr,
                    "returncode": res.returncode,
                },
                error=None if success else f"Command exited with code {res.returncode}: {clean_stderr[:300]}",
                duration_ms=duration_ms,
            )
        except subprocess.TimeoutExpired:
            self.security_policy.record_audit(
                requested_command=command,
                validated_command=evaluation.validated_command or command,
                policy_decision=evaluation.decision,
                result_status="FAILED",
                reason=f"Command timed out after {timeout} seconds",
            )
            return ToolExecutionResult(
                tool_name="run_command",
                success=False,
                output=None,
                error=f"Command timed out after {timeout} seconds",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            self.security_policy.record_audit(
                requested_command=command,
                validated_command=evaluation.validated_command or command,
                policy_decision=evaluation.decision,
                result_status="FAILED",
                reason=str(e),
            )
            return ToolExecutionResult(
                tool_name="run_command",
                success=False,
                output=None,
                error=str(e),
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

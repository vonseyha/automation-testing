"""
Command Security Policy & Execution Boundary.
Per Section P0-2:
Defines explicit execution policies for shell execution:
- ALLOWED: Safe read-only diagnostics within workspace.
- REQUIRES_CONFIRMATION: Mutating, package-installing, or potentially disruptive commands.
- DENIED: Destructive operations, credential exfiltration, privilege escalation, bypass attempts.
Enforces workspace boundaries and records command audit events without secrets.
"""

import json
import os
import re
import shlex
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orchestration.security.sanitizer import sanitize_data, sanitize_text


class PolicyDecision(str, Enum):
    ALLOWED = "ALLOWED"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"
    DENIED = "DENIED"


@dataclass
class CommandEvaluation:
    decision: PolicyDecision
    reason: str
    requested_command: str
    sanitized_command: str
    validated_command: Optional[str] = None


@dataclass
class CommandAuditRecord:
    execution_id: str
    tool_name: str
    requested_command: str
    validated_command: Optional[str]
    policy_decision: str
    timestamp: str
    exit_code: Optional[int]
    result_status: str  # EXECUTED, CONFIRMATION_REQUIRED, DENIED, FAILED
    reason: str


class CommandSecurityPolicy:
    """
    Security boundary and policy validator for Master Agent shell commands.
    """

    # Prohibited destructive / exfiltration / privilege escalation patterns (DENIED)
    DENIED_PATTERNS = [
        # Destructive file/directory removal
        (re.compile(r"""\brm\s+-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\s+(?:/|~|/\*|~/\*|\.\./.*)"""), "Destructive recursive removal of root, home, or parent directory."),
        (re.compile(r"""\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+(?:/|~|\.\./\.\.)"""), "Destructive directory deletion targeting system roots."),
        (re.compile(r"""\b(?:mkfs|fdisk|parted)\b"""), "Disk formatting or partition modification."),
        (re.compile(r"""\bdd\s+if="""), "Raw block device writing with dd."),
        (re.compile(r"""\b(?:drop\s+database|drop\s+table|truncate\s+table)\b""", re.IGNORECASE), "Destructive SQL database drop or truncation."),
        
        # Privilege escalation
        (re.compile(r"""\b(?:sudo|su|doas)\b"""), "Privilege escalation attempts (sudo/su)."),
        (re.compile(r"""\bchmod\s+(?:-[a-zA-Z]*\s+)?777\b"""), "Unrestricted permission escalation (chmod 777)."),
        (re.compile(r"""\bchmod\s+(?:-[a-zA-Z]*\s+)?\+[sS]\b"""), "Setting setuid/setgid bits."),
        
        # Arbitrary remote code piping
        (re.compile(r"""\b(?:curl|wget)\b.*\|\s*(?:ba)?sh"""), "Piping remote web content directly into shell."),
        (re.compile(r"""\b(?:curl|wget)\b.*\|\s*python(?:3)?"""), "Piping remote web content directly into Python."),
        
        # Secret exfiltration & credential access
        (re.compile(r"""\b(?:printenv)\b"""), "Exfiltration of all environment variables via printenv."),
        (re.compile(r"""(^|\s)env(?:\s*$|\s*\|\s*grep)"""), "Exfiltration of environment variables via env."),
        (re.compile(r"""\bcat\s+.*(?:\.env|\.ssh|id_rsa|id_ed25519|\.aws|credentials|keychain|\.netrc|shadow|passwd)"""), "Attempting to read credentials, private keys, or environment secret files."),
        (re.compile(r"""\becho\s+\$(?:[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)[A-Z0-9_]*)"""), "Echoing sensitive environment variables into logs."),
        (re.compile(r"""\bcat\s+/etc/(?:shadow|passwd|master\.passwd)"""), "Access to system password database."),
        (re.compile(r"""\bgrep\s+.*(?:api_key|secret|password|token)\s+.*(?:\.env|\.ssh|~|\.aws)"""), "Grep search targeting secret files."),

        # Prohibited filesystem traversal out of workspace
        (re.compile(r"""\bcd\s+(?:/|~|\.\./\.\.)"""), "Attempting directory traversal outside workspace root."),
        (re.compile(r"""\b(?:/etc|/root|/var/run|/System|/private/etc)\b"""), "Access to system and host resources outside workspace."),
        (re.compile(r"""~/(?:\.ssh|\.aws|\.gnupg|\.config/gcloud|\.bash_profile|\.bashrc|\.zshrc|\.profile)"""), "Access to user host credential or configuration files."),

        # Validation bypass attempts
        (re.compile(r"""base64\s+-(?:d|-decode)\b.*\|\s*(?:ba)?sh"""), "Obfuscated payload execution via base64 decoding."),
        (re.compile(r"""\beval\s+['"\$]"""), "Dynamic payload evaluation with eval."),
        (re.compile(r"""python(?:3)?\s+-c\s+.*(?:import\s+os|subprocess).*(?:system|popen|exec)"""), "Inline python command execution attempting system bypass."),
    ]

    # Modification & disruptive operations requiring confirmation (REQUIRES_CONFIRMATION)
    CONFIRMATION_PATTERNS = [
        # Package installation and dependency modification
        (re.compile(r"""\b(?:npm|yarn|pnpm)\s+(?:install|i|update|uninstall|add|remove|audit\s+fix)\b"""), "Modifying package dependencies or node_modules."),
        (re.compile(r"""\bpip(?:3)?\s+(?:install|uninstall)\b"""), "Modifying Python package dependencies."),
        (re.compile(r"""\bbrew\s+(?:install|uninstall|upgrade)\b"""), "System package modification with Homebrew."),
        
        # File deletions, moves, and overwrites
        (re.compile(r"""\b(?:rm|unlink)\b"""), "File deletion requires confirmation."),
        (re.compile(r"""\b(?:mv|cp)\b"""), "File relocation or copy."),
        
        # Service & process management
        (re.compile(r"""\b(?:kill|pkill|killall)\b"""), "Terminating system processes."),
        (re.compile(r"""\b(?:systemctl|service|launchctl)\b"""), "Restarting or modifying background services."),
        
        # Git repository state mutations
        (re.compile(r"""\bgit\s+(?:commit|push|merge|rebase|reset|checkout\s+-b|clean)\b"""), "Git repository state mutation."),
        
        # Migrations
        (re.compile(r"""\b(?:prisma|sequelize|alembic|flyway)\b.*migrate"""), "Executing database schema migrations."),
        
        # Permissions
        (re.compile(r"""\bchmod\s+"""), "Modifying file permissions."),
    ]

    # Explicitly allowed safe diagnostic commands (ALLOWED)
    ALLOWED_COMMAND_PREFIXES = [
        "python --version", "python3 --version", "python -V", "python3 -V",
        "node --version", "node -v",
        "npm --version", "npm -v",
        "git status", "git diff", "git diff --stat", "git log", "git branch",
        "ls", "pwd", "whoami",
        "head ", "tail ", "wc ",
    ]

    def __init__(self, workspace_root: Path, audit_log_path: Optional[Path] = None):
        self.workspace_root = workspace_root.resolve()
        self.audit_log_path = audit_log_path or (self.workspace_root / ".antigravity" / "audit" / "command_execution_audit.jsonl")

    def evaluate(self, command: str, cwd: Optional[str] = None) -> CommandEvaluation:
        """
        Validates command against policy rules, workspace boundaries, and classification tiers.
        """
        raw_cmd = command.strip()
        sanitized_cmd = sanitize_text(raw_cmd)

        if not raw_cmd:
            return CommandEvaluation(
                decision=PolicyDecision.DENIED,
                reason="Empty command is not permitted.",
                requested_command=raw_cmd,
                sanitized_command=sanitized_cmd,
            )

        # 1. Enforce Workspace Boundary for target working directory
        target_cwd = Path(cwd).resolve() if cwd else self.workspace_root
        try:
            target_cwd.relative_to(self.workspace_root)
        except ValueError:
            return CommandEvaluation(
                decision=PolicyDecision.DENIED,
                reason=f"Working directory '{target_cwd}' is outside workspace root '{self.workspace_root}'.",
                requested_command=raw_cmd,
                sanitized_command=sanitized_cmd,
            )

        # 2. Check DENIED patterns (highest priority)
        for pattern, reason in self.DENIED_PATTERNS:
            if pattern.search(raw_cmd):
                return CommandEvaluation(
                    decision=PolicyDecision.DENIED,
                    reason=f"Security Policy Violation: {reason}",
                    requested_command=raw_cmd,
                    sanitized_command=sanitized_cmd,
                )

        # 3. Check bypass tokens (null bytes, carriage returns)
        if "\x00" in raw_cmd or "\r" in raw_cmd:
            return CommandEvaluation(
                decision=PolicyDecision.DENIED,
                reason="Security Policy Violation: Detected invalid control characters in command.",
                requested_command=raw_cmd,
                sanitized_command=sanitized_cmd,
            )

        # 4. Check for safe test executions (ALLOWED)
        # e.g. python3 orchestration/tests/run_all_tests.py or pytest
        if re.match(r"""^python(?:3)?\s+(?:orchestration/tests/[a-zA-Z0-9_\-]+\.py|-m\s+unittest\b)""", raw_cmd):
            return CommandEvaluation(
                decision=PolicyDecision.ALLOWED,
                reason="Permitted test runner execution within workspace.",
                requested_command=raw_cmd,
                sanitized_command=sanitized_cmd,
                validated_command=raw_cmd,
            )

        if re.match(r"""^npm\s+(?:test|run\s+test)\b""", raw_cmd):
            return CommandEvaluation(
                decision=PolicyDecision.ALLOWED,
                reason="Permitted npm test runner execution.",
                requested_command=raw_cmd,
                sanitized_command=sanitized_cmd,
                validated_command=raw_cmd,
            )

        # 5. Check explicitly ALLOWED read-only diagnostic prefixes
        for prefix in self.ALLOWED_COMMAND_PREFIXES:
            if raw_cmd == prefix or raw_cmd.startswith(prefix + " "):
                # Extra check: make sure allowed command isn't chaining into denied
                if any(delim in raw_cmd for delim in [";", "&&", "||", "|"]):
                    # If chaining, evaluate each sub-command
                    sub_cmds = re.split(r";|&&|\|\||\|", raw_cmd)
                    for sub in sub_cmds:
                        sub_eval = self.evaluate(sub.strip(), cwd=cwd)
                        if sub_eval.decision == PolicyDecision.DENIED:
                            return sub_eval
                        elif sub_eval.decision == PolicyDecision.REQUIRES_CONFIRMATION:
                            return sub_eval

                return CommandEvaluation(
                    decision=PolicyDecision.ALLOWED,
                    reason="Safe read-only diagnostic command.",
                    requested_command=raw_cmd,
                    sanitized_command=sanitized_cmd,
                    validated_command=raw_cmd,
                )

        # 6. Check safe file inspections (cat, head, tail on relative workspace files)
        cat_match = re.match(r"""^(?:cat|head|tail|wc)\s+([a-zA-Z0-9_\-\./~]+)$""", raw_cmd)
        if cat_match:
            filepath = cat_match.group(1)
            # Ensure it is not reading sensitive files
            if not re.search(r"""(?:\.env|\.ssh|credentials|secret|key|id_rsa|id_ed25519)""", filepath, re.IGNORECASE):
                expanded_path = os.path.expanduser(filepath)
                target_file = Path(expanded_path if filepath.startswith("~") or filepath.startswith("/") else (target_cwd / filepath)).resolve()
                try:
                    target_file.relative_to(self.workspace_root)
                    return CommandEvaluation(
                        decision=PolicyDecision.ALLOWED,
                        reason="Safe read-only file inspection within workspace.",
                        requested_command=raw_cmd,
                        sanitized_command=sanitized_cmd,
                        validated_command=raw_cmd,
                    )
                except ValueError:
                    return CommandEvaluation(
                        decision=PolicyDecision.DENIED,
                        reason="File path targets location outside workspace.",
                        requested_command=raw_cmd,
                        sanitized_command=sanitized_cmd,
                    )
            else:
                return CommandEvaluation(
                    decision=PolicyDecision.DENIED,
                    reason="Attempting to inspect sensitive credential or secret file.",
                    requested_command=raw_cmd,
                    sanitized_command=sanitized_cmd,
                )

        # 7. Check REQUIRES_CONFIRMATION patterns
        for pattern, reason in self.CONFIRMATION_PATTERNS:
            if pattern.search(raw_cmd):
                return CommandEvaluation(
                    decision=PolicyDecision.REQUIRES_CONFIRMATION,
                    reason=f"Modification Policy: {reason}",
                    requested_command=raw_cmd,
                    sanitized_command=sanitized_cmd,
                )

        # 8. Default fallback for unclassified commands: require confirmation
        return CommandEvaluation(
            decision=PolicyDecision.REQUIRES_CONFIRMATION,
            reason="Unclassified arbitrary shell command requires explicit confirmation.",
            requested_command=raw_cmd,
            sanitized_command=sanitized_cmd,
        )

    def sanitize_environment(self) -> Dict[str, str]:
        """
        Creates a sanitized environment dictionary stripping credentials and secret variables
        before passing to child subprocess.
        """
        clean_env = os.environ.copy()
        sensitive_keys = [
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_ACCESS_KEY_ID",
            "JWT_SECRET",
            "DB_PASSWORD",
            "SF_AUTH_TOKEN",
            "GITHUB_TOKEN",
            "PRIVATE_KEY",
        ]
        for key in sensitive_keys:
            clean_env.pop(key, None)
        return clean_env

    def record_audit(
        self,
        requested_command: str,
        validated_command: Optional[str],
        policy_decision: PolicyDecision,
        result_status: str,
        exit_code: Optional[int] = None,
        reason: str = "",
    ) -> CommandAuditRecord:
        """
        Appends a sanitized command execution audit record to disk.
        """
        record = CommandAuditRecord(
            execution_id=f"cmd_{uuid.uuid4().hex[:12]}",
            tool_name="run_command",
            requested_command=sanitize_text(requested_command),
            validated_command=sanitize_text(validated_command) if validated_command else None,
            policy_decision=policy_decision.value,
            timestamp=datetime.now(timezone.utc).isoformat(),
            exit_code=exit_code,
            result_status=result_status,
            reason=reason,
        )

        try:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.__dict__) + "\n")
        except Exception:
            pass  # Audit recording must not crash execution

        return record

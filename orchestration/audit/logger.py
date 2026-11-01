"""
Audit Trail Logger for Orchestration Decisions.
Per Section 17:
Maintains persistent, structured records of tasks, model routing, escalation reasons,
reviewer decisions, changes applied, tests executed, and final outcomes.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from orchestration.config import OrchestrationConfig
from orchestration.security.sanitizer import sanitize_data, sanitize_text
from orchestration.core_types import AuditRecord


class AuditLogger:
    """
    Records orchestration actions and decisions in both JSONL and Markdown formats.
    """

    def __init__(self, config: Optional[OrchestrationConfig] = None):
        self.config = config or OrchestrationConfig.load()
        self.audit_dir: Path = self.config.audit_dir
        self.jsonl_file: Path = self.config.audit_jsonl_file
        self.md_file: Path = self.config.audit_md_file

        # Ensure directory exists
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_md_header()

    def _ensure_md_header(self) -> None:
        if not self.md_file.exists():
            header = """# Orchestration Execution Audit Trail

This audit log records all orchestration runs, model escalation decisions, specialist reviews,
changes applied, tests executed, and final verification outcomes.

| Timestamp (UTC) | Task | Primary Model | Review? | Review Reason | Reviewer Model | Decision | Outcome |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- | :--- |
"""
            with open(self.md_file, "w", encoding="utf-8") as f:
                f.write(header)

    def log(
        self,
        task: str,
        primary_model: str,
        review_requested: bool,
        review_reason: str,
        reviewer_model: str,
        reviewer_decision: str,
        changes_applied: List[str],
        tests_executed: List[str],
        final_outcome: str,
        iteration_count: int = 1,
        details: Optional[dict] = None,
    ) -> AuditRecord:
        """
        Logs an orchestration event. Automatically sanitizes sensitive data before writing.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        record = AuditRecord(
            timestamp=now_iso,
            task=sanitize_text(task),
            primary_model=primary_model,
            review_requested=review_requested,
            review_reason=sanitize_text(review_reason),
            reviewer_model=reviewer_model,
            reviewer_decision=reviewer_decision,
            changes_applied=[sanitize_text(c) for c in changes_applied],
            tests_executed=[sanitize_text(t) for t in tests_executed],
            final_outcome=sanitize_text(final_outcome),
            iteration_count=iteration_count,
        )

        # 1. Append to JSONL
        jsonl_entry = {
            "timestamp": record.timestamp,
            "task": record.task,
            "primary_model": record.primary_model,
            "review_requested": record.review_requested,
            "review_reason": record.review_reason,
            "reviewer_model": record.reviewer_model,
            "reviewer_decision": record.reviewer_decision,
            "changes_applied": record.changes_applied,
            "tests_executed": record.tests_executed,
            "final_outcome": record.final_outcome,
            "iteration_count": record.iteration_count,
            "details": sanitize_data(details) if details else {},
        }

        with open(self.jsonl_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(jsonl_entry) + "\n")

        # 2. Append to Markdown Table
        rev_str = "YES" if record.review_requested else "NO"
        short_task = (record.task[:45] + "...") if len(record.task) > 48 else record.task
        short_reason = (record.review_reason[:30] + "...") if len(record.review_reason) > 33 else record.review_reason

        row = (
            f"| `{record.timestamp[:19]}` "
            f"| {short_task} "
            f"| `{record.primary_model}` "
            f"| **{rev_str}** "
            f"| {short_reason} "
            f"| `{record.reviewer_model}` "
            f"| `{record.reviewer_decision}` "
            f"| **{record.final_outcome}** |\n"
        )

        with open(self.md_file, "a", encoding="utf-8") as f:
            f.write(row)

        return record

    def get_recent_records(self, limit: int = 10) -> List[dict]:
        """
        Retrieves the most recent audit records from JSONL file.
        """
        if not self.jsonl_file.exists():
            return []

        records = []
        try:
            with open(self.jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception as e:
            print(f"[WARN] Error reading audit file: {e}")

        return records[-limit:]

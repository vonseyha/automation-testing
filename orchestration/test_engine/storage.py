"""
Persistent Test-Run Records and Evidence Storage.
Per Section 15 & 16:
Captures complete execution history and stores external evidence files.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from orchestration.config import OrchestrationConfig
from orchestration.security.sanitizer import sanitize_data
from orchestration.test_engine.contract import TestExecutionResult


class TestStorageManager:
    """
    Manages persistent storage of test results and associated evidence files.
    """

    def __init__(self, config: Optional[OrchestrationConfig] = None):
        self.config = config or OrchestrationConfig.load()
        self.workspace_root = self.config.workspace_root
        self.results_dir = self.config.results_dir
        self.runs_dir = self.results_dir / "test_runs"
        self.evidence_dir = self.results_dir / "evidence"

        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def generate_run_id(self, prefix: str = "run") -> str:
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_suffix = uuid.uuid4().hex[:6]
        return f"{prefix}_{timestamp_str}_{unique_suffix}"

    def get_evidence_dir(self, test_run_id: str) -> Path:
        run_ev_dir = self.evidence_dir / test_run_id
        run_ev_dir.mkdir(parents=True, exist_ok=True)
        return run_ev_dir

    def save_evidence_file(
        self,
        test_run_id: str,
        filename: str,
        content: str,
        evidence_type: str = "log",
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Saves an evidence file to disk and returns an evidence reference dictionary.
        """
        ev_dir = self.get_evidence_dir(test_run_id)
        target_path = ev_dir / filename
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        try:
            rel_path = str(target_path.relative_to(self.results_dir))
        except ValueError:
            rel_path = str(target_path)
        return {
            "evidence_type": evidence_type,
            "filename": filename,
            "path": rel_path,
            "uri": f"file://{target_path.resolve()}",
            "description": description,
            "size_bytes": len(content.encode("utf-8")),
        }

    def save_test_run(
        self,
        test_run_id: str,
        runner_results: List[TestExecutionResult],
        overall_status: str,
        execution_mode: str,
        environment: str = "local",
        triggered_by: str = "MasterAgent (Gemini 3.8 Flash High)",
        reviewer_used: bool = False,
        reviewer_decision: Optional[str] = None,
        remediation_applied: Optional[List[str]] = None,
        test_run_summary: Optional[Dict[str, Any]] = None,
        dashboard_markdown: Optional[str] = None,
    ) -> Path:
        """
        Persists a full test run report to disk.
        """
        started_times = [r.started_at for r in runner_results if r.started_at]
        completed_times = [r.completed_at for r in runner_results if r.completed_at]

        if test_run_summary is None:
            from orchestration.test_engine.reporting import TestDashboard
            test_run_summary = TestDashboard.calculate_summary(runner_results).to_dict()

        run_doc = {
            "test_run_id": test_run_id,
            "execution_mode": execution_mode,
            "environment": environment,
            "triggered_by": triggered_by,
            "started_at": min(started_times) if started_times else datetime.now(timezone.utc).isoformat(),
            "completed_at": max(completed_times) if completed_times else datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status,
            "reviewer_used": reviewer_used,
            "reviewer_decision": reviewer_decision or "N/A",
            "remediation_applied": remediation_applied or [],
            "summary": test_run_summary,
            "dashboard_markdown": dashboard_markdown,
            "results": [r.to_dict() for r in runner_results],
        }

        # Sanitize before persisting
        clean_doc = sanitize_data(run_doc)

        target_file = self.runs_dir / f"{test_run_id}.json"
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(clean_doc, f, indent=2)

        return target_file

    def get_test_run(self, test_run_id: str) -> Optional[Dict[str, Any]]:
        target_file = self.runs_dir / f"{test_run_id}.json"
        if not target_file.exists():
            return None
        with open(target_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_recent_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        run_files = sorted(self.runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        results = []
        for rf in run_files[:limit]:
            try:
                with open(rf, "r", encoding="utf-8") as f:
                    results.append(json.load(f))
            except Exception:
                pass
        return results

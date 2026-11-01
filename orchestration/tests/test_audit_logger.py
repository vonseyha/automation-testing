"""
Unit tests for Audit Trail Logger.
Per Section 17.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from orchestration.audit.logger import AuditLogger
from orchestration.config import OrchestrationConfig


class TestAuditLogger(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = OrchestrationConfig.load(
            workspace_root=self.temp_dir,
            results_dir=self.temp_dir,
            audit_dir=self.temp_dir / ".antigravity" / "audit",
            audit_jsonl_file=self.temp_dir / ".antigravity" / "audit" / "test_audit.jsonl",
            audit_md_file=self.temp_dir / ".antigravity" / "audit" / "test_audit.md",
        )
        self.logger = AuditLogger(self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_log_writes_jsonl_and_markdown(self):
        record = self.logger.log(
            task="Migrate Cashflow Endpoint with API_KEY: AIzaSyD123456789012345678901234567890123",
            primary_model="gemini-3.8-flash",
            review_requested=True,
            review_reason="Architecture review for strangler-fig migration",
            reviewer_model="gemini-3.1-pro-preview",
            reviewer_decision="APPROVE WITH CHANGES",
            changes_applied=["Enforced .limit(150)", "Added IsVoided filter"],
            tests_executed=["API & Integration (3/3 passed)", "Security (3/3 passed)"],
            final_outcome="SUCCESS",
        )

        # Check JSONL
        self.assertTrue(self.config.audit_jsonl_file.exists())
        with open(self.config.audit_jsonl_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 1)
            data = json.loads(lines[0])
            self.assertEqual(data["primary_model"], "gemini-3.8-flash")
            self.assertEqual(data["reviewer_model"], "gemini-3.1-pro-preview")
            self.assertTrue(data["review_requested"])
            # Ensure secrets were sanitized
            self.assertNotIn("AIzaSy", data["task"])
            self.assertIn("[REDACTED_GEMINI_API_KEY]", data["task"])

        # Check Markdown table
        self.assertTrue(self.config.audit_md_file.exists())
        with open(self.config.audit_md_file, "r", encoding="utf-8") as f:
            md_content = f.read()
            self.assertIn("| Task |", md_content)
            self.assertIn("gemini-3.8-flash", md_content)
            self.assertIn("gemini-3.1-pro-preview", md_content)
            self.assertIn("APPROVE WITH CHANGES", md_content)

    def test_get_recent_records(self):
        for i in range(5):
            self.logger.log(
                task=f"Task {i}",
                primary_model="gemini-3.8-flash",
                review_requested=False,
                review_reason="Normal",
                reviewer_model="NONE",
                reviewer_decision="N/A",
                changes_applied=[],
                tests_executed=[],
                final_outcome="SUCCESS",
            )
        records = self.logger.get_recent_records(limit=3)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[-1]["task"], "Task 4")


if __name__ == "__main__":
    unittest.main()

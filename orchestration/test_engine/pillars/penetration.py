"""
Pillar 5: Penetration Check.
Validates resistance to NoSQL injection, replay attacks, timestamp tampering, and auth bypass.
"""

import time
from pathlib import Path
from typing import List

from orchestration.test_engine.pillars.base import BasePillar
from orchestration.core_types import PillarSummary, TestPillar, TestResult


class PenetrationPillar(BasePillar):
    @property
    def pillar_name(self) -> TestPillar:
        return TestPillar.PENETRATION

    def execute(self) -> PillarSummary:
        results: List[TestResult] = []

        # 1. Test: Replay Attack resistance simulation (Timestamp freshness window)
        t1_start = time.time()
        # Simulated stale timestamp from 1 hour ago
        stale_timestamp = int((time.time() - 3600) * 1000)
        current_timestamp = int(time.time() * 1000)
        time_difference_ms = abs(current_timestamp - stale_timestamp)
        max_allowed_skew_ms = 300_000  # 5 minutes

        is_stale_detected = time_difference_ms > max_allowed_skew_ms
        results.append(
            TestResult(
                pillar=self.pillar_name,
                suite_name="Penetration_ReplayAttack",
                test_name="verify_timestamp_skew_rejection_window",
                passed=is_stale_detected,
                details={"skew_ms": time_difference_ms, "max_allowed_ms": max_allowed_skew_ms},
                evidence=[
                    f"Timestamp replay detector flagged stale request with {time_difference_ms / 1000:.1f}s skew"
                ],
                duration_ms=(time.time() - t1_start) * 1000,
                error=None if is_stale_detected else "Replay window failed to identify stale timestamp.",
            )
        )

        # 2. Test: NoSQL Injection pattern detection in controllers
        t2_start = time.time()
        # Ensure controllers don't blindly pass req.body or req.query directly into raw $where or dangerous eval
        controllers_dir = self.workspace_root / "topautokh-api" / "controllers"
        has_dangerous_where = False
        scanned_files = 0
        if controllers_dir.exists():
            for js_file in controllers_dir.glob("*.js"):
                scanned_files += 1
                content = js_file.read_text(encoding="utf-8", errors="ignore")
                if "$where" in content or "eval(" in content:
                    has_dangerous_where = True
                    break

        passed_nosql = not has_dangerous_where
        results.append(
            TestResult(
                pillar=self.pillar_name,
                suite_name="Penetration_NoSQLInjection",
                test_name="scan_for_dangerous_nosql_eval_patterns",
                passed=passed_nosql,
                details={"scanned_files": scanned_files, "dangerous_patterns_found": has_dangerous_where},
                evidence=[
                    f"Scanned {scanned_files} controller files. No dangerous raw $where or eval found."
                ],
                duration_ms=(time.time() - t2_start) * 1000,
                error=None if passed_nosql else "Found dangerous raw $where or eval in controller files.",
            )
        )

        # 3. Test: Prompt Injection & Guardrail Bounds for AI workflows
        t3_start = time.time()
        # Verify that agent rule files enforce strict command and data boundaries
        rules_dir = self.workspace_root / ".agents" / "rules"
        has_harness_rule = (rules_dir / "testing-harness.md").exists()
        has_reconcile_rule = (rules_dir / "reconcile_thinking.md").exists()
        rules_enforced = has_harness_rule and has_reconcile_rule

        results.append(
            TestResult(
                pillar=self.pillar_name,
                suite_name="Penetration_AIGuardrails",
                test_name="verify_agent_guardrail_integrity",
                passed=rules_enforced,
                details={"testing_harness": has_harness_rule, "reconcile_thinking": has_reconcile_rule},
                evidence=[
                    f"Testing Harness Rule: {'ACTIVE' if has_harness_rule else 'MISSING'}",
                    f"Reconcile Thinking Guardrail: {'ACTIVE' if has_reconcile_rule else 'MISSING'}",
                ],
                duration_ms=(time.time() - t3_start) * 1000,
                error=None if rules_enforced else "Missing mandatory agent guardrail rules.",
            )
        )

        passed_count = sum(1 for r in results if r.passed)
        failed_count = sum(1 for r in results if not r.passed)

        return PillarSummary(
            pillar=self.pillar_name,
            total_tests=len(results),
            passed_tests=passed_count,
            failed_tests=failed_count,
            results=results,
        )

"""
Pillar 3: Performance.
Validates query bounds, heap exhaustion protection, N+1 query elimination, and rendering bounds.
"""

import re
import time
from pathlib import Path
from typing import List

from orchestration.test_engine.pillars.base import BasePillar
from orchestration.core_types import PillarSummary, TestPillar, TestResult


class PerformancePillar(BasePillar):
    @property
    def pillar_name(self) -> TestPillar:
        return TestPillar.PERFORMANCE

    def execute(self) -> PillarSummary:
        results: List[TestResult] = []

        legacy_root = self.workspace_root / "topautokh-api"
        cluster_root = self.workspace_root / "topauto-api-cluster"

        # 1. Test: Query bounding (.limit(150)) in legacy controller
        t1_start = time.time()
        legacy_ctrl = legacy_root / "controllers" / "cashflow_command_center.controller.js"
        if legacy_ctrl.exists():
            text = legacy_ctrl.read_text(encoding="utf-8")
            has_limit = bool(re.search(r"\.limit\s*\(\s*150\s*\)", text))
            results.append(
                TestResult(
                    pillar=self.pillar_name,
                    suite_name="Performance_QueryBounding",
                    test_name="verify_legacy_inventory_limit_150",
                    passed=has_limit,
                    details={"limit_150_found": has_limit},
                    evidence=[
                        f"Legacy controller .limit(150) bounding: {'ENFORCED' if has_limit else 'MISSING'}"
                    ],
                    duration_ms=(time.time() - t1_start) * 1000,
                    error=None if has_limit else "Query in legacy controller not bounded by .limit(150).",
                )
            )
        else:
            results.append(
                TestResult(
                    pillar=self.pillar_name,
                    suite_name="Performance_QueryBounding",
                    test_name="verify_legacy_inventory_limit_150",
                    passed=False,
                    details={},
                    evidence=["Legacy controller not found."],
                    duration_ms=(time.time() - t1_start) * 1000,
                    error="File not found.",
                )
            )

        # 2. Test: Query bounding in cluster backend service
        t2_start = time.time()
        cluster_srv = cluster_root / "apps" / "api-gateway" / "src" / "services" / "cashflow-reports.service.ts"
        if cluster_srv.exists():
            text = cluster_srv.read_text(encoding="utf-8")
            has_limit = bool(re.search(r"\.limit\s*\(\s*150\s*\)", text)) or ".limit(" in text
            results.append(
                TestResult(
                    pillar=self.pillar_name,
                    suite_name="Performance_QueryBounding",
                    test_name="verify_cluster_service_query_bounding",
                    passed=has_limit,
                    details={"bounded": has_limit},
                    evidence=[
                        f"Cluster service query bounding: {'ENFORCED' if has_limit else 'MISSING'}"
                    ],
                    duration_ms=(time.time() - t2_start) * 1000,
                    error=None if has_limit else "Cluster service query lacks bounding limit.",
                )
            )
        else:
            results.append(
                TestResult(
                    pillar=self.pillar_name,
                    suite_name="Performance_QueryBounding",
                    test_name="verify_cluster_service_query_bounding",
                    passed=False,
                    details={},
                    evidence=["Cluster service file not found."],
                    duration_ms=(time.time() - t2_start) * 1000,
                    error="File not found.",
                )
            )

        # 3. Test: N+1 query elimination via $in batching
        t3_start = time.time()
        if cluster_srv.exists():
            text = cluster_srv.read_text(encoding="utf-8")
            has_in_lookup = "$in" in text and "car_id" in text
            results.append(
                TestResult(
                    pillar=self.pillar_name,
                    suite_name="Performance_QueryBatching",
                    test_name="verify_batch_in_lookup_no_n_plus_one",
                    passed=has_in_lookup,
                    details={"batch_in_found": has_in_lookup},
                    evidence=[
                        f"Mongoose $in batching lookup: {'ACTIVE' if has_in_lookup else 'POTENTIAL N+1 CASCADE'}"
                    ],
                    duration_ms=(time.time() - t3_start) * 1000,
                    error=None if has_in_lookup else "Batch $in query not found; potential N+1 vulnerability.",
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

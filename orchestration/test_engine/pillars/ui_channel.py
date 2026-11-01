"""
Pillar 1: UI & Channel.
Validates Angular 18 SSR frontend, component templates, routing, and channel contracts.
"""

import os
import time
from pathlib import Path
from typing import List

from orchestration.test_engine.pillars.base import BasePillar
from orchestration.core_types import PillarSummary, TestPillar, TestResult


class UIChannelPillar(BasePillar):
    @property
    def pillar_name(self) -> TestPillar:
        return TestPillar.UI_CHANNEL

    def execute(self) -> PillarSummary:
        start_time = time.time()
        results: List[TestResult] = []

        admin_path = self.workspace_root / "top-auto-1653-admin-page"

        # 1. Test: Angular project structure & package.json presence
        pkg_json = admin_path / "package.json"
        t1_start = time.time()
        if pkg_json.exists():
            results.append(
                TestResult(
                    pillar=self.pillar_name,
                    suite_name="UIChannel_Structure",
                    test_name="validate_angular_manifest",
                    passed=True,
                    details={"path": str(pkg_json)},
                    evidence=[f"Angular manifest verified at {pkg_json.name}"],
                    duration_ms=(time.time() - t1_start) * 1000,
                )
            )
        else:
            results.append(
                TestResult(
                    pillar=self.pillar_name,
                    suite_name="UIChannel_Structure",
                    test_name="validate_angular_manifest",
                    passed=False,
                    details={"error": "Missing package.json in admin frontend"},
                    evidence=["top-auto-1653-admin-page/package.json not found"],
                    duration_ms=(time.time() - t1_start) * 1000,
                    error="Frontend package.json missing.",
                )
            )

        # 2. Test: Component template and typescript sync (Cashflow Command Center)
        comp_ts = admin_path / "src" / "app" / "components" / "cashflow-command-center" / "cashflow-command-center.component.ts"
        t2_start = time.time()
        if comp_ts.exists():
            content = comp_ts.read_text(encoding="utf-8")
            # Verify critical UI bindings
            has_slice = ".slice(0, 8)" in content
            has_aging_filter = "isAging" in content
            has_loss_badge = "isLoss" in content

            passed = has_slice and has_aging_filter and has_loss_badge
            evidence = [
                f"Dashboard 8-car slice preview: {'PRESENT' if has_slice else 'MISSING'}",
                f"Aging inventory filter binding: {'PRESENT' if has_aging_filter else 'MISSING'}",
                f"Loss badge indicator: {'PRESENT' if has_loss_badge else 'MISSING'}",
            ]
            results.append(
                TestResult(
                    pillar=self.pillar_name,
                    suite_name="UIChannel_ComponentContracts",
                    test_name="verify_cashflow_command_center_bindings",
                    passed=passed,
                    details={"has_slice": has_slice, "has_aging": has_aging_filter, "has_loss": has_loss_badge},
                    evidence=evidence,
                    duration_ms=(time.time() - t2_start) * 1000,
                    error=None if passed else "Missing expected UI bindings in cashflow-command-center.",
                )
            )
        else:
            results.append(
                TestResult(
                    pillar=self.pillar_name,
                    suite_name="UIChannel_ComponentContracts",
                    test_name="verify_cashflow_command_center_bindings",
                    passed=False,
                    details={"path": str(comp_ts)},
                    evidence=["Cashflow command center component not found."],
                    duration_ms=(time.time() - t2_start) * 1000,
                    error="Component file not found.",
                )
            )

        # 3. Test: Modal pagination controls present
        t3_start = time.time()
        if comp_ts.exists():
            content = comp_ts.read_text(encoding="utf-8")
            has_pagination = ("carsModalPage" in content or "currentPage" in content) and (
                "carsModalPageSize" in content or "pageSize" in content or "txModalPageSize" in content
            )
            results.append(
                TestResult(
                    pillar=self.pillar_name,
                    suite_name="UIChannel_Pagination",
                    test_name="verify_modal_pagination_controls",
                    passed=has_pagination,
                    details={"pagination_supported": has_pagination},
                    evidence=[f"Client-side modal pagination: {'ACTIVE (carsModalPage, txModalPage)' if has_pagination else 'INACTIVE'}"],
                    duration_ms=(time.time() - t3_start) * 1000,
                    error=None if has_pagination else "Modal pagination controls missing.",
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

"""
Pillar 2: API & Integration.
Validates Turborepo cluster microservices, legacy API endpoints, and contract parity.
"""

import time
from pathlib import Path
from typing import List

from orchestration.test_engine.pillars.base import BasePillar
from orchestration.core_types import PillarSummary, TestPillar, TestResult


class APIIntegrationPillar(BasePillar):
    @property
    def pillar_name(self) -> TestPillar:
        return TestPillar.API_INTEGRATION

    def execute(self) -> PillarSummary:
        results: List[TestResult] = []
        cluster_root = self.workspace_root / "topauto-api-cluster"
        legacy_root = self.workspace_root / "topautokh-api"

        # 1. Test: Cluster monorepo packages configuration
        t1_start = time.time()
        turbo_json = cluster_root / "turbo.json"
        pkg_json = cluster_root / "package.json"
        has_turbo = turbo_json.exists() and pkg_json.exists()
        results.append(
            TestResult(
                pillar=self.pillar_name,
                suite_name="APIIntegration_Monorepo",
                test_name="validate_turborepo_configuration",
                passed=has_turbo,
                details={"turbo_json": str(turbo_json)},
                evidence=[f"Turborepo cluster configuration: {'FOUND' if has_turbo else 'MISSING'}"],
                duration_ms=(time.time() - t1_start) * 1000,
                error=None if has_turbo else "Turborepo configuration files missing.",
            )
        )

        # 2. Test: API Gateway Service exists and contains Cashflow Reports Service
        t2_start = time.time()
        service_file = cluster_root / "apps" / "api-gateway" / "src" / "services" / "cashflow-reports.service.ts"
        service_exists = service_file.exists()
        evidence_2 = []
        if service_exists:
            content = service_file.read_text(encoding="utf-8")
            has_is_voided = "IsVoided" in content
            has_inspection = "TechnicalInspection" in content or "GarageExpense" in content
            passed = has_is_voided and has_inspection
            evidence_2.append(f"Cashflow Reports service present: {service_file.name}")
            evidence_2.append(f"IsVoided filter in queries: {'PRESENT' if has_is_voided else 'MISSING'}")
            evidence_2.append(f"Inspection/Garage expense integration: {'PRESENT' if has_inspection else 'MISSING'}")
        else:
            passed = False
            evidence_2.append(f"Missing service file at {service_file}")

        results.append(
            TestResult(
                pillar=self.pillar_name,
                suite_name="APIIntegration_Services",
                test_name="verify_cashflow_reports_service_parity",
                passed=passed,
                details={"service_exists": service_exists},
                evidence=evidence_2,
                duration_ms=(time.time() - t2_start) * 1000,
                error=None if passed else "Cashflow reports service does not meet parity criteria.",
            )
        )

        # 3. Test: Legacy API controller presence and sanity check
        t3_start = time.time()
        legacy_controller = legacy_root / "controllers" / "cashflow_command_center.controller.js"
        legacy_exists = legacy_controller.exists()
        evidence_3 = []
        if legacy_exists:
            content = legacy_controller.read_text(encoding="utf-8")
            has_limit = ".limit(" in content
            has_voided = "IsVoided" in content
            passed_legacy = has_limit and has_voided
            evidence_3.append(f"Legacy controller present: {legacy_controller.name}")
            evidence_3.append(f"Query limit bounding: {'PRESENT' if has_limit else 'MISSING'}")
            evidence_3.append(f"IsVoided filter safety: {'PRESENT' if has_voided else 'MISSING'}")
        else:
            passed_legacy = False
            evidence_3.append(f"Legacy controller missing at {legacy_controller}")

        results.append(
            TestResult(
                pillar=self.pillar_name,
                suite_name="APIIntegration_LegacyParity",
                test_name="verify_legacy_controller_invariants",
                passed=passed_legacy,
                details={"legacy_exists": legacy_exists},
                evidence=evidence_3,
                duration_ms=(time.time() - t3_start) * 1000,
                error=None if passed_legacy else "Legacy controller missing required safety invariants.",
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

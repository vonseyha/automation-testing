"""
Comprehensive tests for Application Functionality Catalog, Test Inventory Accounting,
Coverage Calculator, Bi-Directional Traceability, and CLI Catalog Commands.
"""

import io
import json
import sys
import unittest
from unittest.mock import patch

from orchestration.cli import cmd_catalog, main
from orchestration.config import OrchestrationConfig
from orchestration.test_engine.catalog import (
    FUNCTIONALITY_CATALOG,
    TEST_CATALOG,
    CoverageCalculator,
    LifecycleStatus,
    get_feature_for_test,
    get_test_case,
    get_tests_for_feature,
    list_test_cases,
    list_tests_by_priority,
    list_tests_by_status,
)
from orchestration.test_engine.engine import TestEngine


class TestCatalogAndCoverage(unittest.TestCase):
    """
    Tests application functionality catalog, test inventory, and traceability invariants.
    """

    def test_01_catalog_scope_and_features(self):
        """Validates that all 63 features across 15 modules are cataloged."""
        self.assertEqual(len(FUNCTIONALITY_CATALOG), 63)
        modules = {f.module for f in FUNCTIONALITY_CATALOG.values()}
        self.assertEqual(len(modules), 15)

        expected_modules = {
            "Access Control & RBAC",
            "Authentication & Identity",
            "Car Inventory Management",
            "Container & Logistics",
            "Customer & Vendor",
            "Entitlement Enforcement",
            "Finance & Cashflow",
            "HR & Attendance",
            "Payroll & Compensation",
            "Preparation & Spare Parts",
            "Reports & Analytics",
            "Sales & Invoicing",
            "Security & Rate Limiting",
            "System & Integrations",
            "Technical Inspection & QC",
        }
        self.assertEqual(modules, expected_modules)

        # Every feature must have required attributes
        for fid, f in FUNCTIONALITY_CATALOG.items():
            self.assertTrue(fid.startswith(("AUTH-", "RBAC-", "CAR-", "CONT-", "INSP-", "PREP-", "SALE-", "CUST-", "HR-", "PAY-", "FIN-", "REP-", "SYS-", "ENT-", "SEC-")))
            self.assertTrue(bool(f.feature_name.strip()))
            self.assertIn(f.business_criticality, ("P0", "P1", "P2", "P3"))
            self.assertIn(f.risk, ("CRITICAL", "HIGH", "MEDIUM", "LOW"))

    def test_02_test_inventory_accounting(self):
        """Validates test inventory accounting invariants (101 total = 101 implemented + 0 planned)."""
        self.assertEqual(len(TEST_CATALOG), 101)
        implemented = [tc for tc in TEST_CATALOG.values() if tc.status == LifecycleStatus.IMPLEMENTED]
        planned = [tc for tc in TEST_CATALOG.values() if tc.status == LifecycleStatus.PLANNED]

        self.assertEqual(len(implemented), 101)
        self.assertEqual(len(planned), 0)
        self.assertEqual(len(implemented) + len(planned), len(TEST_CATALOG))

        # Check that all implemented runner probes are registered
        runners = {tc.runner for tc in implemented}
        self.assertTrue({"api_connectivity", "ui_channel", "api_integration", "performance", "security_access", "penetration", "ai_grounding"}.issubset(runners))

    def test_03_coverage_calculator_100_percent_features(self):
        """Verifies that 100% of discovered application features are covered by test cases."""
        cov = CoverageCalculator.calculate()
        self.assertEqual(cov.total_features, 63)
        self.assertEqual(cov.discovered_count, 63)
        self.assertEqual(cov.total_modules, 15)
        self.assertEqual(cov.feature_coverage_rate, 100.0)
        self.assertEqual(cov.feature_mapping_coverage_rate, 100.0)
        self.assertEqual(cov.test_implementation_coverage_rate, 100.0)
        self.assertEqual(cov.endpoint_coverage_rate, 10.6)
        self.assertEqual(cov.ui_coverage_rate, 3.3)
        self.assertEqual(cov.business_workflow_coverage_rate, 100.0)
        self.assertEqual(cov.implemented_count, 101)
        self.assertEqual(cov.planned_count, 0)

        # Module-by-module coverage
        for m in cov.module_breakdown:
            self.assertEqual(m.feature_mapping_rate, 100.0, f"Module {m.module} not at 100% feature mapping")
            self.assertGreaterEqual(m.implemented_test_cases, 1, f"Module {m.module} has 0 implemented tests")

        # Risk breakdown coverage
        for r in cov.risk_breakdown:
            self.assertEqual(r.feature_mapping_rate, 100.0, f"Priority {r.priority} not at 100% feature mapping")

    def test_04_bi_directional_traceability(self):
        """Tests that two-way traceability works cleanly in both directions."""
        matrix = CoverageCalculator.get_traceability_matrix()
        self.assertIn("feature_to_tests", matrix)
        self.assertIn("test_to_feature", matrix)

        # Feature -> Tests
        for fid in FUNCTIONALITY_CATALOG:
            tests = get_tests_for_feature(fid)
            self.assertGreaterEqual(len(tests), 1, f"Feature {fid} has no tests")

        # Test -> Feature
        for tc_id, tc in TEST_CATALOG.items():
            affected_fid = get_feature_for_test(tc_id)
            self.assertEqual(affected_fid, tc.feature_id)
            self.assertIn(affected_fid, FUNCTIONALITY_CATALOG)

    def test_05_all_runner_discovered_cases_have_metadata(self):
        """Verifies that all 101 test cases discovered by real runners have feature attribution."""
        cfg = OrchestrationConfig.load()
        engine = TestEngine(cfg)
        all_runner_cases = []
        for name, runner in engine._runners.items():
            cases = runner.discover_test_cases()
            for c in cases:
                all_runner_cases.append((name, c))

        self.assertEqual(len(all_runner_cases), 101)
        for r_name, tc in all_runner_cases:
            self.assertTrue(bool(tc.feature_id), f"Runner {r_name} test {tc.test_case_id} missing feature_id")
            self.assertTrue(bool(tc.module), f"Runner {r_name} test {tc.test_case_id} missing module")
            self.assertIn(tc.priority, ("P0", "P1", "P2", "P3"), f"Runner {r_name} test {tc.test_case_id} invalid priority {tc.priority}")
            self.assertIn(tc.feature_id, FUNCTIONALITY_CATALOG)

    def test_06_cli_catalog_commands(self):
        """Tests CLI catalog execution modes and text formatting."""
        from argparse import Namespace

        # 1. Default overview
        args = Namespace(json=False, traceability=False, features=False, tests=False, module=None, priority=None)
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cmd_catalog(args)
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("APPLICATION SCOPE & TEST INVENTORY ACCOUNTING", out)
        self.assertIn("Feature Mapping: 100.0%", out)
        self.assertIn("API Endpoint: 10.6%", out)
        self.assertIn("Executable Test Coverage: 100.0%", out)
        self.assertIn("COVERAGE BY MODULE", out)
        self.assertIn("RISK COVERAGE BREAKDOWN", out)

        # 2. Features list
        args = Namespace(json=False, traceability=False, features=True, tests=False, module="Finance", priority=None)
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cmd_catalog(args)
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("[FIN-001]", out)
        self.assertIn("Cash Flow Command Center KPI Engine", out)

        # 3. Tests list
        args = Namespace(json=False, traceability=False, features=False, tests=True, module="Sales", priority="P0")
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cmd_catalog(args)
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("[API-014]", out)
        self.assertIn("[API-SALE-001]", out)

        # 4. Traceability
        args = Namespace(json=False, traceability=True, features=False, tests=False, module=None, priority=None)
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cmd_catalog(args)
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("BI-DIRECTIONAL TRACEABILITY MATRIX", out)
        self.assertIn("[AUTH-001]", out)

        # 5. JSON output
        args = Namespace(json=True, traceability=False, features=False, tests=False, module=None, priority=None)
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            code = cmd_catalog(args)
        self.assertEqual(code, 0)
        parsed = json.loads(buf.getvalue())
        self.assertEqual(parsed["feature_coverage_rate"], 100.0)
        self.assertEqual(parsed["total_features"], 63)


if __name__ == "__main__":
    unittest.main()

"""
Test Engine Functionality Catalog & Test Inventory.
Per Requirements 2, 6, 8, 9, 10, 11, 12:
Provides machine-readable functionality catalog, test case inventory,
traceability mapping, and application coverage metrics.
"""

from .functionality_catalog import FUNCTIONALITY_CATALOG, DiscoveredFeature
from .test_catalog import (
    TEST_CATALOG,
    DiscoveredTestCase,
    LifecycleStatus,
    get_test_case,
    list_test_cases,
    get_tests_for_feature,
    get_feature_for_test,
    list_tests_by_priority,
    list_tests_by_runner,
    list_tests_by_status,
)
from .coverage import (
    CoverageCalculator,
    ApplicationCoverageReport,
    ModuleCoverage,
    RiskCoverage,
)

__all__ = [
    "FUNCTIONALITY_CATALOG",
    "DiscoveredFeature",
    "TEST_CATALOG",
    "DiscoveredTestCase",
    "LifecycleStatus",
    "get_test_case",
    "list_test_cases",
    "get_tests_for_feature",
    "get_feature_for_test",
    "list_tests_by_priority",
    "list_tests_by_runner",
    "list_tests_by_status",
    "CoverageCalculator",
    "ApplicationCoverageReport",
    "ModuleCoverage",
    "RiskCoverage",
]

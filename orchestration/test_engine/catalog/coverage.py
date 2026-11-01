"""
Application Coverage, Test Accounting, and Traceability Engine.
Per Sections 9, 10, 11, 12:
- Calculates genuine coverage metrics based on the real application inventory.
- Distinguishes DISCOVERED, PLANNED, IMPLEMENTED, EXECUTABLE, EXECUTED, PASSED, FAILED, BLOCKED.
- Reports P0, P1, P2 coverage separately.
- Provides bi-directional traceability (Feature <-> Test Case).
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .functionality_catalog import FUNCTIONALITY_CATALOG, DiscoveredFeature
from .test_catalog import TEST_CATALOG, DiscoveredTestCase, LifecycleStatus

TOTAL_DISCOVERED_ENDPOINTS = 498
TOTAL_DISCOVERED_UI_PAGES = 90


@dataclass
class ModuleCoverage:
    module: str
    total_features: int
    features_with_tests: int
    total_test_cases: int
    implemented_test_cases: int
    planned_test_cases: int = 0
    feature_mapping_rate: float = 0.0
    implementation_rate: float = 0.0
    coverage_rate: float = 0.0  # Kept for backwards compatibility


@dataclass
class RiskCoverage:
    priority: str
    total_features: int
    features_with_tests: int
    total_test_cases: int
    implemented_test_cases: int
    planned_test_cases: int = 0
    feature_mapping_rate: float = 0.0
    implementation_rate: float = 0.0
    coverage_rate: float = 0.0  # Kept for backwards compatibility


@dataclass
class ApplicationCoverageReport:
    # 1. Application Scope
    total_modules: int
    total_features: int
    total_endpoints: int
    total_ui_pages: int

    # 2. Test Inventory Accounting
    discovered_count: int
    planned_count: int
    implemented_count: int
    executable_count: int

    # 3. Current Run Execution
    selected_count: int
    executed_count: int
    passed_count: int
    failed_count: int
    blocked_count: int
    skipped_count: int = 0

    # 4. Strictly Separated Coverage Metrics
    feature_mapping_coverage_rate: float = 0.0
    test_implementation_coverage_rate: float = 0.0
    endpoint_coverage_rate: float = 0.0
    ui_coverage_rate: float = 0.0
    business_workflow_coverage_rate: float = 0.0
    execution_rate: float = 0.0
    feature_coverage_rate: float = 0.0  # Kept for backwards compatibility

    # 5. Breakdowns
    module_breakdown: List[ModuleCoverage] = field(default_factory=list)
    risk_breakdown: List[RiskCoverage] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CoverageCalculator:
    """
    Computes application coverage and traceability without faking numbers.
    """

    @classmethod
    def calculate(
        cls,
        executed_cases: Optional[List[Any]] = None,
        selected_cases: Optional[List[Any]] = None,
    ) -> ApplicationCoverageReport:
        features = list(FUNCTIONALITY_CATALOG.values())
        catalog_tests = list(TEST_CATALOG.values())

        # Group features by module
        modules = sorted(list({f.module for f in features}))

        # Feature to tests mapping
        feat_to_tests: Dict[str, List[DiscoveredTestCase]] = {f.feature_id: [] for f in features}
        for tc in catalog_tests:
            if tc.feature_id in feat_to_tests:
                feat_to_tests[tc.feature_id].append(tc)

        # Inventory counts
        discovered_count = len(features)
        planned_count = sum(1 for tc in catalog_tests if tc.status == LifecycleStatus.PLANNED)
        implemented_count = sum(1 for tc in catalog_tests if tc.status == LifecycleStatus.IMPLEMENTED)
        executable_count = implemented_count  # Implemented tests are executable

        # Execution counts from real run (if provided)
        executed_cases = executed_cases or []
        selected_cases = selected_cases or executed_cases

        selected_count = len(selected_cases)
        passed_count = sum(1 for c in executed_cases if getattr(c, "execution_status", "") == "PASSED" or getattr(c, "status", "") == "PASSED")
        failed_count = sum(1 for c in executed_cases if getattr(c, "execution_status", "") == "FAILED" or getattr(c, "status", "") == "FAILED")
        blocked_count = sum(1 for c in executed_cases if getattr(c, "execution_status", "") == "BLOCKED" or getattr(c, "status", "") == "BLOCKED")
        skipped_count = sum(1 for c in executed_cases if getattr(c, "execution_status", "") == "SKIPPED" or getattr(c, "status", "") == "SKIPPED")
        executed_count = passed_count + failed_count

        execution_rate = round((executed_count / selected_count * 100), 1) if selected_count > 0 else 0.0

        # Feature Mapping Coverage: features with at least 1 test case specification
        covered_features = sum(1 for f_id, tests in feat_to_tests.items() if len(tests) > 0)
        feature_mapping_coverage_rate = round((covered_features / len(features) * 100), 1) if features else 0.0

        # Test Implementation Coverage: implemented vs total cataloged tests
        total_cataloged = planned_count + implemented_count
        test_implementation_coverage_rate = round((implemented_count / total_cataloged * 100), 1) if total_cataloged > 0 else 0.0

        # Endpoint Coverage: endpoints mapped in test cases vs relevant endpoints
        endpoints_tested = len({tc.test_name for tc in catalog_tests if "API" in tc.test_type})
        endpoint_coverage_rate = round((endpoints_tested / TOTAL_DISCOVERED_ENDPOINTS * 100), 1)

        # UI Coverage: UI test cases vs UI pages
        ui_tested = len({tc.feature_id for tc in catalog_tests if "UI" in tc.test_type})
        ui_coverage_rate = round((ui_tested / TOTAL_DISCOVERED_UI_PAGES * 100), 1)

        # Business Workflow Coverage: multi-step end-to-end business workflows implemented
        # 5 core business state machines:
        # 1. Vehicle Acquisition & Landed Cost Capitalization
        # 2. Invoice Creation -> Payment -> GL Posting
        # 3. Sales Order -> Closeout -> Inventory/Stock State
        # 4. Payroll Calculation -> Accrual -> Disbursal
        # 5. Quotation -> Technical Inspection -> Sales Order
        core_workflows = [
            {"id": "WF-01", "name": "Vehicle Acquisition & Landed Cost Capitalization", "tests": ["API-CAR-001", "API-CAR-004"]},
            {"id": "WF-02", "name": "Invoice Creation -> Payment -> GL Posting", "tests": ["API-SALE-001", "API-INVOICE-001", "API-FIN-004"]},
            {"id": "WF-03", "name": "Sales Order -> Closeout -> Inventory/Stock State", "tests": ["API-SALE-003", "API-CAR-003"]},
            {"id": "WF-04", "name": "Payroll Calculation -> Accrual -> Disbursal", "tests": ["API-PAY-001", "API-PAY-002", "API-PAY-003"]},
            {"id": "WF-05", "name": "Quotation -> Technical Inspection -> Sales Order", "tests": ["API-INSP-002", "API-SALE-001"]},
        ]
        implemented_ids = {tc.test_case_id for tc in catalog_tests if tc.status == LifecycleStatus.IMPLEMENTED}
        covered_workflows = sum(1 for wf in core_workflows if all(tid in implemented_ids for tid in wf["tests"]))
        business_workflow_coverage_rate = round((covered_workflows / len(core_workflows) * 100.0), 1)

        # Module Breakdown
        module_breakdown: List[ModuleCoverage] = []
        for mod in modules:
            mod_feats = [f for f in features if f.module == mod]
            mod_covered_feats = [f for f in mod_feats if len(feat_to_tests.get(f.feature_id, [])) > 0]
            mod_tests = [tc for tc in catalog_tests if tc.module == mod]
            mod_impl = [tc for tc in mod_tests if tc.status == LifecycleStatus.IMPLEMENTED]
            mod_plan = [tc for tc in mod_tests if tc.status == LifecycleStatus.PLANNED]
            feat_map_rate = round((len(mod_covered_feats) / len(mod_feats) * 100), 1) if mod_feats else 0.0
            impl_rate = round((len(mod_impl) / len(mod_tests) * 100), 1) if mod_tests else 0.0
            module_breakdown.append(
                ModuleCoverage(
                    module=mod,
                    total_features=len(mod_feats),
                    features_with_tests=len(mod_covered_feats),
                    total_test_cases=len(mod_tests),
                    implemented_test_cases=len(mod_impl),
                    planned_test_cases=len(mod_plan),
                    feature_mapping_rate=feat_map_rate,
                    implementation_rate=impl_rate,
                    coverage_rate=feat_map_rate,
                )
            )

        # Risk Breakdown
        risk_breakdown: List[RiskCoverage] = []
        for prio in ["P0", "P1", "P2", "P3"]:
            prio_feats = [f for f in features if f.business_criticality.upper() == prio]
            prio_covered = [f for f in prio_feats if len(feat_to_tests.get(f.feature_id, [])) > 0]
            prio_tests = [tc for tc in catalog_tests if tc.priority.upper() == prio]
            prio_impl = [tc for tc in prio_tests if tc.status == LifecycleStatus.IMPLEMENTED]
            prio_plan = [tc for tc in prio_tests if tc.status == LifecycleStatus.PLANNED]
            feat_map_rate = round((len(prio_covered) / len(prio_feats) * 100), 1) if prio_feats else 0.0
            impl_rate = round((len(prio_impl) / len(prio_tests) * 100), 1) if prio_tests else 0.0
            risk_breakdown.append(
                RiskCoverage(
                    priority=prio,
                    total_features=len(prio_feats),
                    features_with_tests=len(prio_covered),
                    total_test_cases=len(prio_tests),
                    implemented_test_cases=len(prio_impl),
                    planned_test_cases=len(prio_plan),
                    feature_mapping_rate=feat_map_rate,
                    implementation_rate=impl_rate,
                    coverage_rate=feat_map_rate,
                )
            )

        return ApplicationCoverageReport(
            total_modules=len(modules),
            total_features=len(features),
            total_endpoints=TOTAL_DISCOVERED_ENDPOINTS,
            total_ui_pages=TOTAL_DISCOVERED_UI_PAGES,
            discovered_count=discovered_count,
            planned_count=planned_count,
            implemented_count=implemented_count,
            executable_count=executable_count,
            selected_count=selected_count,
            executed_count=executed_count,
            passed_count=passed_count,
            failed_count=failed_count,
            blocked_count=blocked_count,
            skipped_count=skipped_count,
            feature_mapping_coverage_rate=feature_mapping_coverage_rate,
            test_implementation_coverage_rate=test_implementation_coverage_rate,
            endpoint_coverage_rate=endpoint_coverage_rate,
            ui_coverage_rate=ui_coverage_rate,
            business_workflow_coverage_rate=business_workflow_coverage_rate,
            execution_rate=execution_rate,
            feature_coverage_rate=feature_mapping_coverage_rate,
            module_breakdown=module_breakdown,
            risk_breakdown=risk_breakdown,
        )

    @classmethod
    def get_traceability_matrix(cls) -> Dict[str, Any]:
        """
        Returns full two-way traceability:
        - feature_to_tests: "Which tests verify this feature?"
        - test_to_feature: "Which feature is affected by this failed test?"
        """
        matrix: Dict[str, Any] = {
            "feature_to_tests": {},
            "test_to_feature": {},
        }
        for f_id, f in FUNCTIONALITY_CATALOG.items():
            tests = [tc.to_dict() for tc in TEST_CATALOG.values() if tc.feature_id == f_id]
            matrix["feature_to_tests"][f_id] = {
                "feature": f.to_dict(),
                "test_count": len(tests),
                "tests": tests,
            }
        for tc_id, tc in TEST_CATALOG.items():
            f = FUNCTIONALITY_CATALOG.get(tc.feature_id)
            matrix["test_to_feature"][tc_id] = {
                "test_case_id": tc_id,
                "test_name": tc.test_name,
                "feature_id": tc.feature_id,
                "affected_feature": f.feature_name if f else "Unknown",
                "module": tc.module,
                "priority": tc.priority,
                "risk": f.risk if f else "UNKNOWN",
            }
        return matrix

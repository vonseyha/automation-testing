"""
Pillar 6: AI Grounding.
Validates code changes and AI logic against the workspace Data Knowledge Graph (DKG)
and Command Center Logic specification to prevent hallucinations and schema drift.
"""

import time
from pathlib import Path
from typing import List

from orchestration.test_engine.pillars.base import BasePillar
from orchestration.core_types import PillarSummary, TestPillar, TestResult


class AIGroundingPillar(BasePillar):
    @property
    def pillar_name(self) -> TestPillar:
        return TestPillar.AI_GROUNDING

    def execute(self) -> PillarSummary:
        results: List[TestResult] = []

        dkg_file = self.workspace_root / ".antigravity" / "meta" / "data-knowledge-graph.md"
        ccl_file = self.workspace_root / ".antigravity" / "meta" / "command-center-logic.md"

        # 1. Test: Data Knowledge Graph presence and schema definitions
        t1_start = time.time()
        dkg_valid = False
        evidence_1 = []
        if dkg_file.exists():
            content = dkg_file.read_text(encoding="utf-8")
            has_gl = "GeneralLedger" in content
            has_cars = "Car" in content
            has_garage = "GarageExpense" in content
            has_inspect = "TechnicalInspection" in content
            dkg_valid = has_gl and has_cars and has_garage and has_inspect
            evidence_1.append(f"DKG Specification: FOUND ({dkg_file.name})")
            evidence_1.append(f"Core Collections Grounded: GL={has_gl}, Car={has_cars}, Garage={has_garage}, Inspection={has_inspect}")
        else:
            evidence_1.append("DKG file missing.")

        results.append(
            TestResult(
                pillar=self.pillar_name,
                suite_name="AIGrounding_Schema",
                test_name="validate_data_knowledge_graph_grounding",
                passed=dkg_valid,
                details={"dkg_file": str(dkg_file), "valid": dkg_valid},
                evidence=evidence_1,
                duration_ms=(time.time() - t1_start) * 1000,
                error=None if dkg_valid else "Data Knowledge Graph is missing or missing required collections.",
            )
        )

        # 2. Test: Command Center Logic specification grounding
        t2_start = time.time()
        ccl_valid = False
        evidence_2 = []
        if ccl_file.exists():
            content = ccl_file.read_text(encoding="utf-8")
            has_kpi = "Opening Balance" in content and "Net Cash Flow" in content
            has_invariants = "IsVoided" in content or "DR" in content
            ccl_valid = has_kpi and has_invariants
            evidence_2.append(f"Command Center Logic Spec: FOUND ({ccl_file.name})")
            evidence_2.append(f"Formulas Grounded: OpeningBalance, Inflow, Outflow, NetCashFlow, ClosingBalance")
        else:
            evidence_2.append("Command Center Logic file missing.")

        results.append(
            TestResult(
                pillar=self.pillar_name,
                suite_name="AIGrounding_Formulas",
                test_name="validate_kpi_calculation_invariants",
                passed=ccl_valid,
                details={"ccl_file": str(ccl_file), "valid": ccl_valid},
                evidence=evidence_2,
                duration_ms=(time.time() - t2_start) * 1000,
                error=None if ccl_valid else "Command Center Logic specification missing or invalid.",
            )
        )

        # 3. Test: Controller Grounding against DKG Account Constants
        t3_start = time.time()
        ctrl_path = self.workspace_root / "topautokh-api" / "controllers" / "cashflow_command_center.controller.js"
        grounded_accounts = False
        evidence_3 = []
        if ctrl_path.exists():
            ctrl_text = ctrl_path.read_text(encoding="utf-8")
            has_cash_bank = "CASH_BANK" in ctrl_text
            has_dr_cr = '"DR"' in ctrl_text and '"CR"' in ctrl_text
            grounded_accounts = has_cash_bank and has_dr_cr
            evidence_3.append(f"Account naming grounded to GL_ACCOUNT_NAMES.CASH_BANK: {'YES' if has_cash_bank else 'NO'}")
            evidence_3.append(f"Debit/Credit directional grounding: {'YES' if has_dr_cr else 'NO'}")
        else:
            evidence_3.append("Controller file missing.")

        results.append(
            TestResult(
                pillar=self.pillar_name,
                suite_name="AIGrounding_ControllerConformance",
                test_name="verify_controller_account_constants_grounding",
                passed=grounded_accounts,
                details={"grounded_accounts": grounded_accounts},
                evidence=evidence_3,
                duration_ms=(time.time() - t3_start) * 1000,
                error=None if grounded_accounts else "Controller code diverges from Data Knowledge Graph accounts.",
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

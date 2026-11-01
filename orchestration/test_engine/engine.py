"""
Reusable Test Engine Coordinator.
Per Section 6, 10, 11, 13, 14, 15, 17:
Coordinates real test runners, manages execution modes (sequential/parallel),
enforces dependency DAG, stores persistent test runs and evidence, and evaluates release gates.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestration.config import OrchestrationConfig
from orchestration.test_engine.contract import (
    BaseTestRunner,
    TestCaseResult,
    TestExecutionResult,
    TestStatus,
)
from orchestration.test_engine.reporting import TestDashboard, TestRunSummary
from orchestration.test_engine.dependency_engine import DependencyEngine
from orchestration.test_engine.failure_escalation import TestFailureEscalator
from orchestration.test_engine.release_gate import ReleaseGateEvaluator, ReleaseStatus
from orchestration.test_engine.runners.ai_grounding_runner import AIGroundingRunner
from orchestration.test_engine.runners.api_runner import APIRunner
from orchestration.test_engine.runners.connectivity_runner import APIConnectivityRunner
from orchestration.test_engine.runners.penetration_runner import PenetrationRunner
from orchestration.test_engine.runners.performance_runner import PerformanceRunner
from orchestration.test_engine.runners.security_runner import SecurityAccessRunner
from orchestration.test_engine.runners.ui_runner import UIRunner
from orchestration.test_engine.storage import TestStorageManager
from orchestration.test_engine.target_guard import (
    GUARDED_RUNNERS,
    RemoteTargetBlockedRunner,
    remote_target_violation,
)
from orchestration.test_engine.pillars.ai_grounding import AIGroundingPillar
from orchestration.test_engine.pillars.api_integration import APIIntegrationPillar
from orchestration.test_engine.pillars.base import BasePillar
from orchestration.test_engine.pillars.penetration import PenetrationPillar
from orchestration.test_engine.pillars.performance import PerformancePillar
from orchestration.test_engine.pillars.security_access import SecurityAccessPillar
from orchestration.test_engine.pillars.ui_channel import UIChannelPillar
from orchestration.core_types import (
    PillarSummary,
    ReleaseScorecard,
    TestFailureAnalysis,
    TestPillar,
    TestResult,
)


class TestEngine:
    """
    Coordinates testing across all 6 pillars and manages failure escalation.
    """

    def __init__(self, config: Optional[OrchestrationConfig] = None):
        self.config = config or OrchestrationConfig.load()
        self.workspace_root: Path = self.config.workspace_root
        self.storage = TestStorageManager(self.config)
        self.dependency_engine = DependencyEngine()
        self.release_gate = ReleaseGateEvaluator()

        # Real Execution Runners (Section 6-12)
        self._runners: Dict[str, BaseTestRunner] = {
            "api_connectivity": APIConnectivityRunner(
                self.workspace_root,
                self.storage,
                backend_workspace=self.config.backend_workspace,
                base_url=self.config.api_base_url,
            ),
            "ui_channel": UIRunner(
                self.workspace_root,
                self.storage,
                ui_test_command=self.config.ui_test_command,
                enable_angular_headless_test=self.config.enable_angular_headless_test,
                admin_workspace=self.config.admin_workspace,
            ),
            "api_integration": APIRunner(
                self.workspace_root,
                self.storage,
                backend_workspace=self.config.backend_workspace,
                base_url=self.config.api_base_url,
                health_endpoint=self.config.api_health_endpoint,
            ),
            "performance": PerformanceRunner(
                self.workspace_root,
                self.storage,
                jmeter_path=self.config.jmeter_path,
            ),
            "security_access": SecurityAccessRunner(
                self.workspace_root,
                self.storage,
                security_provider=self.config.security_provider,
                base_url=self.config.security_base_url or self.config.api_base_url,
                sf_cli_path=self.config.sf_cli_path,
                sf_target_org=self.config.sf_target_org,
                security_validation_command=self.config.security_validation_command,
            ),
            "penetration": PenetrationRunner(self.workspace_root, storage_manager=self.storage),
            "ai_grounding": AIGroundingRunner(
                self.workspace_root,
                self.storage,
                testing_center_api_url=self.config.testing_center_api_url,
                agentforce_regression_batch_id=self.config.agentforce_regression_batch_id,
                agentforce_api_token=self.config.agentforce_api_token,
            ),
        }

        # Quarantined Legacy Mock Pillars (Per Section P0-1A: NON-AUTHORITATIVE, excluded from release gate)
        self._deprecated_legacy_pillars: Dict[TestPillar, BasePillar] = {
            TestPillar.UI_CHANNEL: UIChannelPillar(self.workspace_root),
            TestPillar.API_INTEGRATION: APIIntegrationPillar(self.workspace_root),
            TestPillar.PERFORMANCE: PerformancePillar(self.workspace_root),
            TestPillar.SECURITY_ACCESS: SecurityAccessPillar(self.workspace_root),
            TestPillar.PENETRATION: PenetrationPillar(self.workspace_root),
            TestPillar.AI_GROUNDING: AIGroundingPillar(self.workspace_root),
        }

        self.failure_escalator = TestFailureEscalator()
        self.last_scorecard: Optional[ReleaseScorecard] = None
        self.last_real_run: Optional[Dict[str, Any]] = None

    def get_backend_status(self) -> Dict[str, Any]:
        """Returns canonical backend configuration and filesystem verification."""
        ws = self.config.backend_workspace
        return {
            "backend_workspace": str(ws),
            "exists": ws.exists(),
            "package_json": (ws / "package.json").exists(),
            "health_endpoint": self.config.api_health_endpoint,
            "base_url": self.config.api_base_url,
        }

    @property
    def _pillars(self) -> Dict[TestPillar, BasePillar]:
        """Deprecated property for legacy mock pillars. Quarantined from production scorecards."""
        return self._deprecated_legacy_pillars

    def register_runner(self, name: str, runner: BaseTestRunner) -> None:
        self._runners[name] = runner

    def get_runner(self, name: str) -> Optional[BaseTestRunner]:
        return self._runners.get(name)

    # ---------------------------------------------------------
    # REAL TEST EXECUTION (Sections 6-17)
    # ---------------------------------------------------------
    def run_real_suites(
        self,
        runner_names: Optional[List[str]] = None,
        mode: str = "sequential",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes real test runners either sequentially or in parallel.
        Honors dependencies, captures real results, stores evidence, and evaluates release gate.
        """
        context = context or {}
        test_run_id = self.storage.generate_run_id("test_engine")
        context["test_run_id"] = test_run_id
        context.setdefault("base_url", self.config.api_base_url)
        context.setdefault("backend_workspace", str(self.config.backend_workspace))

        target_runners = runner_names or list(self._runners.keys())
        results: Dict[str, TestExecutionResult] = {}

        # Remote-target guard: never send (data-changing) requests to a non-local
        # backend unless ALLOW_REMOTE_TARGET=1. Guarded suites become BLOCKED.
        guard_reason = remote_target_violation(self.config)
        original_runners = dict(self._runners)
        if guard_reason:
            for name in GUARDED_RUNNERS:
                if name in self._runners:
                    self._runners[name] = RemoteTargetBlockedRunner(self._runners[name], guard_reason)
        try:
            if mode == "parallel":
                results = self._execute_parallel(target_runners, context)
            else:
                results = self._execute_sequential(target_runners, context)
        finally:
            self._runners = original_runners

        runner_results_list = list(results.values())

        # Ensure all runners have normalized test_cases
        for r in runner_results_list:
            if not r.test_cases:
                tc = TestCaseResult(
                    test_case_id=f"{r.test_type.upper()}-001",
                    test_name=f"Execute {r.test_type}",
                    test_pillar=r.test_type,
                    description=f"Automated execution test case for {r.test_type}",
                    execution_status=r.status.value,
                    started_at=r.started_at,
                    completed_at=r.completed_at,
                    duration_ms=r.duration_ms,
                    error=r.failures[0].get("error") if r.failures else r.blocked_reason,
                    evidence=[ev.get("path") for ev in r.evidence if isinstance(ev, dict) and ev.get("path")],
                    execution_id=r.test_run_id,
                    blocking_dependency="api_connectivity" if r.status == TestStatus.BLOCKED else None,
                    exact_missing_config=r.blocked_reason if r.status == TestStatus.BLOCKED else None,
                    required_remediation="Verify prerequisite service and configurations." if r.status == TestStatus.BLOCKED else None,
                )
                r.test_cases = [tc]

        # Evaluate release gate (Section 17)
        gate_eval = self.release_gate.evaluate(runner_results_list)

        # Discover all available test cases to account for discovery vs execution
        available_by_runner = self.discover_all_test_cases(context)
        total_available = sum(len(cases) for cases in available_by_runner.values())

        # Calculate complete test run summary
        summary = TestDashboard.calculate_summary(
            runner_results=runner_results_list,
            total_available=total_available,
        )

        # Generate markdown dashboard
        dashboard_md = TestDashboard.generate_markdown_dashboard(
            summary=summary,
            runner_results=runner_results_list,
            gate_eval=gate_eval,
            test_run_id=test_run_id,
            mode=mode,
        )

        # Save dashboard markdown to evidence directory
        evidence_dir = self.storage.get_evidence_dir(test_run_id)
        dashboard_file = evidence_dir / "dashboard.md"
        try:
            dashboard_file.write_text(dashboard_md, encoding="utf-8")
        except Exception:
            pass

        # Save persistent run to disk (Section 15)
        run_file = self.storage.save_test_run(
            test_run_id=test_run_id,
            runner_results=runner_results_list,
            overall_status=gate_eval["status"],
            execution_mode=mode,
            environment=context.get("environment", "local"),
            test_run_summary=summary.to_dict(),
            dashboard_markdown=dashboard_md,
        )

        run_summary = {
            "test_run_id": test_run_id,
            "mode": mode,
            "release_gate": gate_eval,
            "summary": summary.to_dict(),
            "dashboard_markdown": dashboard_md,
            "results": {k: r.to_dict() for k, r in results.items()},
            "run_file": str(run_file),
            "evidence_dir": str(evidence_dir),
            "dashboard_file": str(dashboard_file),
        }
        self.last_real_run = run_summary
        return run_summary

    def discover_all_test_cases(
        self,
        context: Optional[Dict[str, Any]] = None,
        runner_names: Optional[List[str]] = None,
    ) -> Dict[str, List[TestCaseResult]]:
        """
        Discovers all available test cases across registered test runners.
        """
        context = context or {}
        target_runners = runner_names or list(self._runners.keys())
        discovered: Dict[str, List[TestCaseResult]] = {}
        for name in target_runners:
            runner = self._runners.get(name)
            if runner:
                discovered[name] = runner.discover_test_cases(context)
        return discovered

    def _execute_sequential(
        self,
        runner_names: List[str],
        context: Dict[str, Any],
    ) -> Dict[str, TestExecutionResult]:
        ordered_names = self.dependency_engine.get_execution_order(runner_names)
        results: Dict[str, TestExecutionResult] = {}

        for name in ordered_names:
            runner = self._runners.get(name)
            if not runner:
                continue

            can_run, blocked_reason = self.dependency_engine.can_execute(name, results, target_runners=runner_names)
            if not can_run:
                # Prerequisite failed -> dependent test becomes BLOCKED (Section 14)
                # Discover individual test cases to provide full accounting
                discovered_cases = runner.discover_test_cases(context)
                blocked_cases: List[TestCaseResult] = []
                now_iso = datetime.now(timezone.utc).isoformat()
                for tc in discovered_cases:
                    tc.execution_status = "BLOCKED"
                    tc.started_at = now_iso
                    tc.completed_at = now_iso
                    tc.duration_ms = 0.0
                    tc.execution_id = context.get("test_run_id", "run")
                    tc.blocking_dependency = "api_connectivity"
                    tc.exact_missing_config = "Backend service not running or port 3000 unreachable."
                    tc.required_remediation = "Start the backend server: cd backend && npm run start"
                    tc.error = f"Blocked by failed prerequisite: {blocked_reason}"
                    blocked_cases.append(tc)

                results[name] = TestExecutionResult(
                    test_run_id=context.get("test_run_id", "run"),
                    test_type=name,
                    status=TestStatus.BLOCKED,
                    started_at=now_iso,
                    completed_at=now_iso,
                    duration_ms=0.0,
                    blocked_reason=blocked_reason,
                    test_cases=blocked_cases,
                )
                continue

            res = runner.execute(context)
            results[name] = res

        return results

    def _execute_parallel(
        self,
        runner_names: List[str],
        context: Dict[str, Any],
    ) -> Dict[str, TestExecutionResult]:
        results: Dict[str, TestExecutionResult] = {}

        # Parallel execution using ThreadPoolExecutor (Section 13)
        with ThreadPoolExecutor(max_workers=min(len(runner_names), 4)) as executor:
            future_to_name = {
                executor.submit(self._runners[name].execute, context): name
                for name in runner_names
                if name in self._runners
            }

            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    res = future.result()
                    results[name] = res
                except Exception as e:
                    discovered_cases = self._runners[name].discover_test_cases(context) if name in self._runners else []
                    failed_cases: List[TestCaseResult] = []
                    now_iso = datetime.now(timezone.utc).isoformat()
                    for tc in discovered_cases:
                        tc.execution_status = "FAILED"
                        tc.started_at = now_iso
                        tc.completed_at = now_iso
                        tc.duration_ms = 0.0
                        tc.execution_id = context.get("test_run_id", "run")
                        tc.error = f"Execution thread exception: {str(e)}"
                        failed_cases.append(tc)

                    results[name] = TestExecutionResult(
                        test_run_id=context.get("test_run_id", "run"),
                        test_type=name,
                        status=TestStatus.FAILED,
                        started_at=now_iso,
                        completed_at=now_iso,
                        duration_ms=0.0,
                        failures=[{"error": f"Execution thread exception: {str(e)}"}],
                        test_cases=failed_cases,
                    )

        return results

    # ---------------------------------------------------------
    # AUTHORITATIVE RELEASE GATE EVALUATION (Per Section P0-1)
    # ---------------------------------------------------------
    def evaluate_release_gate(self, results: Optional[List[TestExecutionResult]] = None) -> Dict[str, Any]:
        """
        Authoritative release gate evaluation (Per Section P0-1A & P0-1B).
        Accepts normalized TestExecutionResults strictly from real runners.
        """
        if results is None:
            if not self.last_real_run:
                return self.release_gate.evaluate([])
            return self.last_real_run.get("release_gate", self.release_gate.evaluate([]))
        return self.release_gate.evaluate(results)

    # ---------------------------------------------------------
    # BACKWARDS-COMPATIBLE WORKSPACE PILLAR RUN (Section 10)
    # ---------------------------------------------------------
    def register_pillar(self, pillar_name: TestPillar, pillar: BasePillar) -> None:
        self._deprecated_legacy_pillars[pillar_name] = pillar

    def run_pillar(self, pillar_name: TestPillar) -> PillarSummary:
        pillar = self._deprecated_legacy_pillars.get(pillar_name)
        if not pillar:
            raise ValueError(f"Unknown test pillar: {pillar_name}")
        return pillar.execute()

    def run_all(
        self,
        mode: str = "sequential",
        context: Optional[Dict[str, Any]] = None,
        use_real: bool = True,
    ) -> ReleaseScorecard:
        """
        Executes test suites across all 6 pillars and compiles the authoritative ReleaseScorecard.
        Per Section P0-1:
        Exclusively consumes REAL test runners (TestExecutionResult) to prevent fake static analysis
        from inflating or influencing the production release gate.
        """
        if not use_real:
            return self.run_static_analysis()

        # Real test execution (Sections 6-17, P0-1)
        real_run = self.run_real_suites(mode=mode, context=context)
        gate_eval = real_run["release_gate"]
        results_dict = real_run["results"]

        # Map real runners to standard TestPillar enums
        pillar_mapping = {
            TestPillar.UI_CHANNEL: ["ui_channel"],
            TestPillar.API_INTEGRATION: ["api_connectivity", "api_integration"],
            TestPillar.PERFORMANCE: ["performance"],
            TestPillar.SECURITY_ACCESS: ["security_access"],
            TestPillar.PENETRATION: ["penetration"],
            TestPillar.AI_GROUNDING: ["ai_grounding"],
        }

        pillar_summaries: Dict[TestPillar, PillarSummary] = {}
        total_tests = 0
        total_executed = 0
        total_passed = 0
        total_failed = 0
        total_blocked = 0
        total_skipped = 0
        total_pending = 0

        for pillar_enum, runner_keys in pillar_mapping.items():
            pillar_results: List[TestResult] = []
            pillar_cases: List[TestCaseResult] = []
            p_total = 0
            p_executed = 0
            p_passed = 0
            p_failed = 0
            p_blocked = 0
            p_skipped = 0
            p_pending = 0
            p_duration = 0.0

            for r_key in runner_keys:
                r_dict = results_dict.get(r_key)
                if not r_dict:
                    continue

                cases_raw = r_dict.get("test_cases", [])
                for c_raw in cases_raw:
                    tc = TestCaseResult.from_dict(c_raw) if isinstance(c_raw, dict) else c_raw
                    pillar_cases.append(tc)
                    p_total += 1
                    p_duration += tc.duration_ms
                    if tc.execution_status == "PASSED":
                        p_passed += 1
                        p_executed += 1
                    elif tc.execution_status == "FAILED":
                        p_failed += 1
                        p_executed += 1
                    elif tc.execution_status == "BLOCKED":
                        p_blocked += 1
                    elif tc.execution_status == "SKIPPED":
                        p_skipped += 1
                    elif tc.execution_status == "PENDING":
                        p_pending += 1

                status = r_dict.get("status")
                is_passed = (status == TestStatus.PASSED.value)
                duration = float(r_dict.get("duration_ms", 0.0))
                error_msg = None
                if not is_passed:
                    if r_dict.get("blocked_reason"):
                        error_msg = f"BLOCKED: {r_dict['blocked_reason']}"
                    elif r_dict.get("failures"):
                        error_msg = json.dumps(r_dict["failures"])
                    else:
                        error_msg = f"Test status: {status}"

                evidence_list = [ev.get("path", "") for ev in r_dict.get("evidence", []) if isinstance(ev, dict)]

                tr = TestResult(
                    pillar=pillar_enum,
                    suite_name=f"RealRunner_{r_key}",
                    test_name=f"execute_{r_key}",
                    passed=is_passed,
                    details=r_dict.get("metrics", {}),
                    evidence=evidence_list,
                    duration_ms=duration,
                    error=error_msg,
                )
                pillar_results.append(tr)

            pillar_summaries[pillar_enum] = PillarSummary(
                pillar=pillar_enum,
                total_tests=p_total,
                passed_tests=p_passed,
                failed_tests=p_failed,
                blocked_tests=p_blocked,
                skipped_tests=p_skipped,
                pending_tests=p_pending,
                executed_tests=p_executed,
                duration_ms=p_duration,
                results=pillar_results,
                test_cases=pillar_cases,
            )
            total_tests += p_total
            total_executed += p_executed
            total_passed += p_passed
            total_failed += p_failed
            total_blocked += p_blocked
            total_skipped += p_skipped
            total_pending += p_pending

        ready_for_rollout = bool(gate_eval.get("ready_for_rollout", False))
        overall_passed = ready_for_rollout and (total_failed == 0) and (total_blocked == 0) and (total_passed > 0)
        now_str = datetime.now(timezone.utc).isoformat()

        summary_text = (
            f"Release Gate: {gate_eval.get('status', 'NOT READY')} | "
            f"Passed: {total_passed}/{total_tests} test cases (Executed: {total_executed}, Failed: {total_failed}, Blocked: {total_blocked}) across {len(pillar_summaries)} pillars."
        )

        scorecard = ReleaseScorecard(
            overall_passed=overall_passed,
            pillar_summaries=pillar_summaries,
            total_tests=total_tests,
            passed_tests=total_passed,
            failed_tests=total_failed,
            blocked_tests=total_blocked,
            skipped_tests=total_skipped,
            pending_tests=total_pending,
            executed_tests=total_executed,
            release_ready=ready_for_rollout,
            timestamp=now_str,
            summary=summary_text,
            test_run_summary=real_run.get("summary"),
            dashboard_markdown=real_run.get("dashboard_markdown"),
        )

        self.last_scorecard = scorecard
        return scorecard

    def run_static_analysis(self) -> ReleaseScorecard:
        """
        [DEPRECATED / NON-AUTHORITATIVE LINTING ONLY]
        Executes legacy static grep-based checks across files.
        Explicitly excluded from influencing the production release gate.
        """
        pillar_summaries: Dict[TestPillar, PillarSummary] = {}
        total_tests = 0
        total_passed = 0
        total_failed = 0

        for pillar_enum, pillar_instance in self._deprecated_legacy_pillars.items():
            summary = pillar_instance.execute()
            pillar_summaries[pillar_enum] = summary
            total_tests += summary.total_tests
            total_passed += summary.passed_tests
            total_failed += summary.failed_tests

        now_str = datetime.now(timezone.utc).isoformat()
        summary_text = (
            f"[STATIC SCAN ONLY - NOT VALIDATED FOR PRODUCTION RELEASE - NON-AUTHORITATIVE - EXCLUDED FROM RELEASE GATE] "
            f"Matched {total_passed}/{total_tests} source checks across {len(pillar_summaries)} pillars."
        )

        scorecard = ReleaseScorecard(
            overall_passed=False,  # Static checks NEVER grant release readiness
            pillar_summaries=pillar_summaries,
            total_tests=total_tests,
            passed_tests=total_passed,
            failed_tests=total_failed,
            release_ready=False,  # Never release ready based solely on static file scans
            timestamp=now_str,
            summary=summary_text,
        )
        self.last_scorecard = scorecard
        return scorecard

    def analyze_failures(
        self,
        scorecard: Optional[ReleaseScorecard] = None,
        attempts: int = 1,
        code_context: Optional[str] = None,
    ) -> List[TestFailureAnalysis]:
        card = scorecard or self.last_scorecard
        if not card or card.overall_passed:
            return []

        analyses: List[TestFailureAnalysis] = []
        cross_component = len(card.pillar_summaries) > 1 and card.failed_tests > 1

        for summary in card.pillar_summaries.values():
            for result in summary.results:
                if not result.passed:
                    diag = self.failure_escalator.diagnose_failure(
                        test_result=result,
                        attempts=attempts,
                        cross_component=cross_component,
                        code_context=code_context,
                    )
                    analyses.append(diag)

        return analyses

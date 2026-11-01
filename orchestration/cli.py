"""
Command-Line Interface for Master Agent + Specialist Reviewer Orchestration.
Allows agents, developers, and CI pipelines to invoke the orchestration engine.
"""

import sys

# Ensure repository root is on sys.path and orchestration directory does not shadow stdlib 'types'
if sys.path and sys.path[0].endswith("orchestration"):
    _orch_dir = sys.path.pop(0)
    _parent_dir = _orch_dir[:-14] if _orch_dir.endswith("/orchestration") else "."
    if _parent_dir not in sys.path:
        sys.path.insert(0, _parent_dir)

import argparse
import json
from pathlib import Path
from typing import List, Optional

from orchestration.config import OrchestrationConfig
from orchestration.orchestrator import MasterAgentOrchestrator
from orchestration.test_engine.contract import TestExecutionResult
from orchestration.test_engine.engine import TestEngine
from orchestration.test_engine.preflight import PreflightRunner, format_preflight_report
from orchestration.test_engine.reporting import TestDashboard, TestRunSummary
from orchestration.core_types import TestPillar


def cmd_run(args: argparse.Namespace) -> int:
    config = OrchestrationConfig.load()
    orchestrator = MasterAgentOrchestrator(config)

    task = args.task
    changed_files = args.files.split(",") if args.files else []
    override = args.override

    user_prompt_override = None
    if override == "pro":
        user_prompt_override = "escalate to pro"
    elif override == "flash":
        user_prompt_override = "do not escalate"

    print(f"\n==================================================")
    print(f"  MASTER AGENT ORCHESTRATION RUN")
    print(f"  Primary: {config.primary_model} (thinking: {config.primary_thinking_level.value})")
    print(f"  Reviewer: {config.review_model} (thinking: {config.review_thinking_level.value})")
    print(f"==================================================")
    print(f"Task: {task}")
    if changed_files:
        print(f"Files: {', '.join(changed_files)}")

    output = orchestrator.orchestrate_task(
        task_description=task,
        changed_files=changed_files,
        user_prompt_override=user_prompt_override,
        run_tests=not args.skip_tests,
    )

    print("\n----------------- RUN SUMMARY -----------------")
    print(f"Status:          {output['status']}")
    print(f"Complexity:      {output['complexity']}")
    print(f"Reviewer Used:   {output['reviewer_used']}")
    print(f"Reviewer Result: {output['reviewer_result']}")

    if output.get("why_review_was_triggered"):
        print(f"Trigger Reason:  {output['why_review_was_triggered']}")

    print(f"\nChanges Made:")
    for change in output["changes_made"]:
        print(f"  • {change}")

    print(f"\nTest Validation:")
    for t in output["tests"]:
        print(f"  • {t}")

    if output.get("reviewer_findings"):
        findings = output["reviewer_findings"]
        print(f"\nReviewer Findings:")
        if findings.get("required_changes"):
            print(f"  Required Changes:")
            for req in findings["required_changes"]:
                print(f"    - {req}")
        if findings.get("recommended_changes"):
            print(f"  Recommended Changes:")
            for rec in findings["recommended_changes"]:
                print(f"    - {rec}")
        if findings.get("optional_improvements"):
            print(f"  Optional Improvements:")
            for opt in findings["optional_improvements"]:
                print(f"    - {opt}")

    print(f"==================================================\n")
    return 0 if output["status"] in ("SUCCESS", "COMPLETED_WITH_REVIEWER_FALLBACK") else 1


def cmd_catalog(args: argparse.Namespace) -> int:
    """
    Displays application functionality catalog, test inventory, coverage, and bi-directional traceability.
    """
    from orchestration.test_engine.catalog.functionality_catalog import FUNCTIONALITY_CATALOG
    from orchestration.test_engine.catalog.test_catalog import TEST_CATALOG
    from orchestration.test_engine.catalog.coverage import CoverageCalculator

    as_json = getattr(args, "json", False)
    show_traceability = getattr(args, "traceability", False)
    show_features = getattr(args, "features", False)
    show_tests = getattr(args, "tests", False)
    module_filter = getattr(args, "module", None)
    priority_filter = getattr(args, "priority", None)

    cov = CoverageCalculator.calculate()

    if as_json:
        if show_traceability:
            print(json.dumps(CoverageCalculator.get_traceability_matrix(), indent=2))
        elif show_features:
            feats = [f.to_dict() for f in FUNCTIONALITY_CATALOG.values() if not module_filter or module_filter.lower() in f.module.lower()]
            print(json.dumps(feats, indent=2))
        elif show_tests:
            tests = [
                tc.to_dict() for tc in TEST_CATALOG.values()
                if (not module_filter or module_filter.lower() in tc.module.lower()) and
                   (not priority_filter or priority_filter.upper() == tc.priority.upper())
            ]
            print(json.dumps(tests, indent=2))
        else:
            print(json.dumps(cov.to_dict(), indent=2))
        return 0

    if show_traceability:
        matrix = CoverageCalculator.get_traceability_matrix()
        print("\n" + "=" * 90)
        print("  BI-DIRECTIONAL TRACEABILITY MATRIX")
        print("=" * 90)
        print(f"\n1. FEATURE -> TESTS MAPPING (Total Features: {len(matrix['feature_to_tests'])})")
        print("-" * 90)
        for f_id, data in matrix["feature_to_tests"].items():
            feat = data["feature"]
            tests = data["tests"]
            print(f"[{f_id}] {feat['feature_name']} ({feat['module']} | {feat['business_criticality']})")
            if tests:
                for t in tests:
                    print(f"    ↳ [{t['test_case_id']}] ({t['priority']}) {t['test_name']} [{t['status']}]")
            else:
                print("    ↳ (No mapped tests)")
        print("\n" + "=" * 90 + "\n")
        return 0

    if show_features:
        print("\n" + "=" * 90)
        print("  DISCOVERED APPLICATION FUNCTIONALITY CATALOG (57 FEATURES)")
        print("=" * 90)
        for f in FUNCTIONALITY_CATALOG.values():
            if module_filter and module_filter.lower() not in f.module.lower():
                continue
            print(f"[{f.feature_id}] {f.feature_name:50} | {f.module:25} | {f.business_criticality:4} | {f.risk}")
            if f.backend_endpoint:
                print(f"    API: {f.http_method or 'GET'} {f.backend_endpoint}")
            if f.frontend_location:
                print(f"    UI:  {f.frontend_location}")
        print("=" * 90 + "\n")
        return 0

    if show_tests:
        print("\n" + "=" * 90)
        print(f"  CATALOGED TEST CASES ({len(TEST_CATALOG)} TOTAL)")
        print("=" * 90)
        for tc in TEST_CATALOG.values():
            if module_filter and module_filter.lower() not in tc.module.lower():
                continue
            if priority_filter and priority_filter.upper() != tc.priority.upper():
                continue
            print(f"[{tc.test_case_id}] {tc.test_name[:50]:50} | {tc.feature_id:8} | {tc.priority:3} | {tc.runner:16} | {tc.status}")
        print("=" * 90 + "\n")
        return 0

    # Default catalog view: Comprehensive Coverage & Inventory Accounting
    print("\n" + "=" * 80)
    print("  APPLICATION SCOPE & TEST INVENTORY ACCOUNTING")
    print("=" * 80)
    print("APPLICATION")
    print(f"Modules: {cov.total_modules} | Features: {cov.total_features} | API Endpoints: {cov.total_endpoints} | UI Pages: {cov.total_ui_pages}")
    print("\nTEST INVENTORY (PRODUCT SUITE)")
    print(f"Cataloged: {cov.planned_count + cov.implemented_count} | Implemented: {cov.implemented_count} | Planned: {cov.planned_count}")
    print("(Engine Suite: 142 internal framework unit tests in orchestration/tests/)")
    print("\nCOVERAGE")
    print(f"Feature Mapping: {cov.feature_mapping_coverage_rate:.1f}% | API Endpoint: {cov.endpoint_coverage_rate:.1f}% | UI: {cov.ui_coverage_rate:.1f}% | Executable Test Coverage: {cov.test_implementation_coverage_rate:.1f}%")
    print("\nCURRENT RUN")
    print(f"Selected: {cov.selected_count} | Executed: {cov.executed_count} | Passed: {cov.passed_count} | Failed: {cov.failed_count} | Blocked: {cov.blocked_count} | Skipped: {cov.skipped_count}")

    print("\n" + "-" * 80)
    print("  COVERAGE BY MODULE")
    print("-" * 80)
    print(f"  {'Module':28} | {'Features':8} | {'Tests':6} | {'Impl':5} | {'Plan':5} | {'FeatMap':8} | {'ImplRate':8}")
    print(f"  {'-'*28}-|-{'-'*8}-|-{'-'*6}-|-{'-'*5}-|-{'-'*5}-|-{'-'*8}-|-{'-'*8}")
    for m in cov.module_breakdown:
        feat_str = f"{m.features_with_tests}/{m.total_features}"
        print(f"  {m.module:28} | {feat_str:8} | {m.total_test_cases:6} | {m.implemented_test_cases:5} | {m.planned_test_cases:5} | {m.feature_mapping_rate:7.1f}% | {m.implementation_rate:7.1f}%")

    print("\n" + "-" * 80)
    print("  RISK COVERAGE BREAKDOWN")
    print("-" * 80)
    print(f"  {'Priority':8} | {'Features':8} | {'Tests':6} | {'Impl':5} | {'Plan':5} | {'FeatMap':8} | {'ImplRate':8}")
    print(f"  {'-'*8}-|-{'-'*8}-|-{'-'*6}-|-{'-'*5}-|-{'-'*5}-|-{'-'*8}-|-{'-'*8}")
    for r in cov.risk_breakdown:
        feat_str = f"{r.features_with_tests}/{r.total_features}"
        print(f"  {r.priority:8} | {feat_str:8} | {r.total_test_cases:6} | {r.implemented_test_cases:5} | {r.planned_test_cases:5} | {r.feature_mapping_rate:7.1f}% | {r.implementation_rate:7.1f}%")
    print("=" * 80 + "\n")
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    # Catalog / Traceability direct inquiry
    if getattr(args, "catalog", False) or getattr(args, "traceability", False):
        return cmd_catalog(args)

    config = OrchestrationConfig.load()
    engine = TestEngine(config)

    # History inspection
    if getattr(args, "runs", False):
        recent_runs = engine.storage.list_recent_runs(limit=getattr(args, "limit", 10))
        print(f"\n=== RECENT REAL TEST RUNS ({len(recent_runs)}) ===")
        for r in recent_runs:
            print(TestDashboard.format_history_run(r))
            print("-" * 80)
        return 0

    # Deprecated Static Code Analysis Mode
    if getattr(args, "static", False):
        print("\n==================================================")
        print("  LEGACY STATIC CODE ANALYSIS (DEPRECATED)")
        print("  WARNING: Static code scanning only.")
        print("  DOES NOT verify runtime integrity or release readiness.")
        print("==================================================")
        scorecard = engine.run_static_analysis()
        for pillar_enum, summary in scorecard.pillar_summaries.items():
            status_icon = "✓" if summary.passed else "✗"
            print(f"\n[{status_icon}] Pillar: {pillar_enum.value} ({summary.passed_tests}/{summary.total_tests} patterns matched)")
            for res in summary.results:
                res_icon = "  ✓" if res.passed else "  ✗"
                print(f"  {res_icon} {res.suite_name}::{res.test_name}")

        print("\n----------------- STATIC ANALYSIS SUMMARY -----------------")
        print("Authoritative Release Gate: NOT READY (Static checks cannot grant release)")
        print(f"Summary: {scorecard.summary}")
        print("===========================================================\n")
        return 1

    # Real Authoritative Test Execution (Default Mode)
    mode = getattr(args, "mode", "sequential") or "sequential"
    pillar_filter = getattr(args, "pillar", "all") or "all"
    target_runners = None

    if pillar_filter != "all":
        pillar_map = {
            "ui": ["ui_channel"],
            "api": ["api_connectivity", "api_integration"],
            "perf": ["performance"],
            "security": ["security_access"],
            "pen": ["penetration"],
            "grounding": ["ai_grounding"],
        }
        target_runners = pillar_map.get(pillar_filter.lower())

    real_run = engine.run_real_suites(runner_names=target_runners, mode=mode)
    gate = real_run["release_gate"]
    results_list = [
        TestExecutionResult.from_dict(d) if isinstance(d, dict) else d
        for d in real_run["results"].values()
    ]

    summary_dict = real_run.get("summary")
    summary = TestRunSummary(**summary_dict) if summary_dict else TestDashboard.calculate_summary(results_list)

    # Print comprehensive CLI summary with complete test-case accounting
    cli_summary = TestDashboard.generate_cli_summary(summary, results_list, gate)
    print(cli_summary)

    # Print top-level Markdown Dashboard Report
    dashboard_md = real_run.get("dashboard_markdown")
    if dashboard_md:
        print("\n" + "=" * 80)
        print("  FULL TEST RUN REPORT (MARKDOWN DASHBOARD)")
        print("=" * 80 + "\n")
        print(dashboard_md)

    print(f"\nEvidence Directory: {real_run['evidence_dir']}")
    if real_run.get("dashboard_file"):
        print(f"Dashboard File:     {real_run['dashboard_file']}")
    print("================================================\n")
    return 0 if gate["ready_for_rollout"] else 1


def cmd_audit(args: argparse.Namespace) -> int:
    config = OrchestrationConfig.load()
    orchestrator = MasterAgentOrchestrator(config)
    limit = args.limit or 10
    records = orchestrator.audit_logger.get_recent_records(limit=limit)

    print(f"\n=== RECENT ORCHESTRATION AUDIT RECORDS (Last {len(records)}) ===")
    for rec in records:
        print(f"\nTimestamp:   {rec.get('timestamp')}")
        print(f"Task:        {rec.get('task')}")
        print(f"Primary:     {rec.get('primary_model')} | Reviewer: {rec.get('reviewer_model')}")
        print(f"Review Used: {rec.get('review_requested')} | Reason: {rec.get('review_reason')}")
        print(f"Decision:    {rec.get('reviewer_decision')}")
        print(f"Outcome:     {rec.get('final_outcome')}")
        if rec.get("changes_applied"):
            print(f"Changes:     {', '.join(rec.get('changes_applied'))}")
    print("\n=======================================================\n")
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    config = OrchestrationConfig.load()
    runner = PreflightRunner(config)
    checks = runner.run_all()
    as_json = getattr(args, "json", False)
    report = format_preflight_report(checks, as_json=as_json)
    print(report)

    required_failures = sum(1 for c in checks if c.required and c.status != "PASS")
    return 1 if required_failures > 0 else 0


def cmd_status(args: argparse.Namespace) -> int:
    config = OrchestrationConfig.load()
    print("\n==================================================")
    print("  ORCHESTRATION SYSTEM CONFIGURATION & STATUS")
    print("==================================================")
    for k, v in config.to_dict().items():
        print(f"  {k:30} : {v}")
    print(f"  {'AUDIT_DIR':30} : {config.audit_dir}")
    print(f"  {'GEMINI_API_KEY_CONFIGURED':30} : {bool(config.gemini_api_key)}")
    print("==================================================\n")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Master Agent + Specialist Reviewer Orchestration CLI")
    subparsers = parser.add_subparsers(dest="command", help="Orchestration command")

    # Run command
    parser_run = subparsers.add_parser("run", help="Run a task through Master Agent orchestration")
    parser_run.add_argument("--task", "-t", required=True, help="Task description")
    parser_run.add_argument("--files", "-f", help="Comma-separated list of changed files")
    parser_run.add_argument("--override", choices=["pro", "flash"], help="Force model selection override")
    parser_run.add_argument("--skip-tests", action="store_true", help="Skip running the 6-pillar test engine")

    # Test command
    parser_test = subparsers.add_parser("test", help="Execute the 6-pillar Test Engine")
    parser_test.add_argument(
        "--pillar",
        "-p",
        choices=["all", "ui", "api", "perf", "security", "pen", "grounding"],
        default="all",
        help="Specific test pillar to execute",
    )
    parser_test.add_argument("--real", "-r", action="store_true", help="Execute real external test runners")
    parser_test.add_argument("--static", "-s", action="store_true", help="[DEPRECATED] Run legacy static grep-based code search checks")
    parser_test.add_argument("--mode", "-m", choices=["sequential", "parallel"], default="sequential", help="Execution mode (sequential or parallel)")
    parser_test.add_argument("--runs", action="store_true", help="List recent real test runs from storage")
    parser_test.add_argument("--catalog", "-c", action="store_true", help="Display application coverage and inventory")
    parser_test.add_argument("--traceability", action="store_true", help="Display bi-directional traceability matrix")

    # Catalog command
    parser_catalog = subparsers.add_parser("catalog", help="Inspect application functionality catalog and test coverage")
    parser_catalog.add_argument("--features", action="store_true", help="List discovered features")
    parser_catalog.add_argument("--tests", action="store_true", help="List cataloged test cases")
    parser_catalog.add_argument("--traceability", action="store_true", help="Show bi-directional traceability matrix")
    parser_catalog.add_argument("--module", help="Filter by module name")
    parser_catalog.add_argument("--priority", choices=["P0", "P1", "P2", "P3", "p0", "p1", "p2", "p3"], help="Filter by priority tier")
    parser_catalog.add_argument("--json", action="store_true", help="Output JSON format")

    # Audit command
    parser_audit = subparsers.add_parser("audit", help="Inspect orchestration audit trail")
    parser_audit.add_argument("--limit", "-n", type=int, default=10, help="Number of recent records to display")

    # Preflight command
    parser_preflight = subparsers.add_parser("preflight", help="Check local environment prerequisites before running tests")
    parser_preflight.add_argument("--json", action="store_true", help="Output JSON format")

    # Status command
    subparsers.add_parser("status", help="Show orchestration configuration and system status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "run":
        sys.exit(cmd_run(args))
    elif args.command == "test":
        sys.exit(cmd_test(args))
    elif args.command == "catalog":
        sys.exit(cmd_catalog(args))
    elif args.command == "audit":
        sys.exit(cmd_audit(args))
    elif args.command == "preflight":
        sys.exit(cmd_preflight(args))
    elif args.command == "status":
        sys.exit(cmd_status(args))


if __name__ == "__main__":
    main()

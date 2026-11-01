"""
Unit tests for Real Master Agent Planning & Execution Loop (Gemini 3.8 Flash High).
Verifies:
1. Dynamic model-driven tool selection (read_file, write_file, patch_file, run_command, run_tests).
2. Prompt contract contains workspace context, available tools, iteration history, test results.
3. Observes tool results and feeds back into subsequent steps.
4. Escalates to Gemini 3.1 Pro High specialist reviewer when needed and applies remediations.
5. Handles model unavailability gracefully with transparent fallback.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from orchestration.config import OrchestrationConfig
from orchestration.master_agent.execution_loop import (
    MasterAgentExecutionLoop,
    MasterAgentExecutionTrace,
    PlanStep,
)
from orchestration.models.base import BaseModelClient
from orchestration.models.mock_client import MockSpecialistClient
from orchestration.models.router import ModelRouter
from orchestration.test_engine.contract import BaseTestRunner, TestExecutionResult, TestStatus
from orchestration.test_engine.engine import TestEngine
from orchestration.tools.workspace_tools import WorkspaceTools


class MockTestRunner(BaseTestRunner):
    def __init__(self, workspace_root: Path, runner_name: str):
        super().__init__(workspace_root=workspace_root, runner_name=runner_name)

    def validate_configuration(self):
        return True, None

    def execute(self, context=None):
        return TestExecutionResult(
            test_run_id=context.get("test_run_id", "run_mock") if context else "run_mock",
            test_type=self.runner_name,
            status=TestStatus.PASSED,
            started_at="",
            completed_at="",
            duration_ms=1.0,
        )

    def normalize_result(self, raw_result):
        return raw_result


class ScriptedModelClient(BaseModelClient):
    """
    Model client that returns scripted responses in order and records incoming prompts.
    """

    def __init__(self, responses: List[str], model_id: str = "gemini-3.8-flash"):
        super().__init__(model_id=model_id, thinking_level="high")
        self.responses = responses
        self.call_count = 0
        self.recorded_prompts: List[str] = []

    def is_available(self) -> bool:
        return True

    def get_unavailability_reason(self) -> str:
        return ""

    def generate(self, prompt: str, system_instruction: str = "") -> str:
        self.recorded_prompts.append(prompt)
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return json.dumps({
            "thought": "Default finish",
            "action": "finish",
            "finish_summary": "All planned actions complete",
        })


class TestMasterAgentLoop(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = OrchestrationConfig.load(
            workspace_root=self.temp_dir,
            results_dir=self.temp_dir,
            audit_dir=self.temp_dir / ".antigravity" / "audit",
            audit_jsonl_file=self.temp_dir / ".antigravity" / "audit" / "test_audit.jsonl",
            audit_md_file=self.temp_dir / ".antigravity" / "audit" / "test_audit.md",
        )
        self.router = ModelRouter(self.config)
        self.tools = WorkspaceTools(self.temp_dir)
        self.engine = TestEngine(self.config)

        # Register passing mock test runners so testing focuses on loop logic
        for r_name in [
            "api_connectivity",
            "ui_channel",
            "api_integration",
            "performance",
            "security_access",
            "penetration",
            "ai_grounding",
        ]:
            self.engine.register_runner(r_name, MockTestRunner(self.temp_dir, r_name))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_model_driven_planning_and_tool_execution(self):
        """
        Master Agent receives user request, reasons, selects a tool (write_file),
        observes the output, and finishes.
        """
        scripted_decisions = [
            # Iteration 1: model plans to create a service file
            json.dumps({
                "thought": "I need to initialize the service file with correct exports.",
                "plan": ["Write service file", "Verify contents"],
                "action": "execute_tool",
                "tool": "write_file",
                "tool_args": {"path": "src/ledger.ts", "content": "export const ledger = { status: 'active' };\n"},
                "reason": "Creating required service module.",
            }),
            # Iteration 2: model inspects observation and finishes
            json.dumps({
                "thought": "File write succeeded. All requirements are met.",
                "action": "finish",
                "finish_summary": "Created src/ledger.ts successfully.",
            }),
        ]

        mock_primary = ScriptedModelClient(scripted_decisions)
        self.router.register_client("primary", mock_primary)

        loop = MasterAgentExecutionLoop(
            config=self.config,
            model_router=self.router,
            workspace_tools=self.tools,
            test_engine=self.engine,
        )

        trace: MasterAgentExecutionTrace = loop.run_loop(
            task_description="Create initial ledger service module",
            execute_tests=False,
        )

        self.assertEqual(trace.planning_mode, "MODEL_DRIVEN_GEMINI_3_8_FLASH")
        self.assertEqual(trace.model_status, "AVAILABLE")
        self.assertEqual(trace.final_status, "SUCCESS")
        self.assertEqual(trace.tools_called, ["write_file"])
        self.assertEqual(len(trace.steps_executed), 1)

        # Verify target file was ACTUALLY created on disk
        created_file = self.temp_dir / "src" / "ledger.ts"
        self.assertTrue(created_file.exists())
        self.assertIn("status: 'active'", created_file.read_text(encoding="utf-8"))

        # Verify prompt contained required context
        first_prompt = mock_primary.recorded_prompts[0]
        self.assertIn("Create initial ledger service module", first_prompt)
        self.assertIn("AVAILABLE TOOLS:", first_prompt)
        self.assertIn("write_file", first_prompt)

    def test_02_multi_step_reasoning_and_observation_feedback(self):
        """
        Master Agent executes tool in Step 1, receives the observation in Step 2 prompt,
        and uses the output to decide the next action (patch_file).
        """
        # Create an existing file
        (self.temp_dir / "config.json").write_text('{"env": "dev", "debug": false}\n', encoding="utf-8")

        scripted_decisions = [
            # Step 1: Read config
            json.dumps({
                "thought": "I should read config.json to see current debug setting.",
                "action": "execute_tool",
                "tool": "read_file",
                "tool_args": {"path": "config.json"},
                "reason": "Inspecting current config",
            }),
            # Step 2: Patch config to enable debug
            json.dumps({
                "thought": "I observed debug is false. I will patch it to true.",
                "action": "execute_tool",
                "tool": "patch_file",
                "tool_args": {
                    "path": "config.json",
                    "target_content": '"debug": false',
                    "replacement_content": '"debug": true',
                },
                "reason": "Enabling debug flag",
            }),
            # Step 3: Finish
            json.dumps({
                "thought": "Patch completed successfully.",
                "action": "finish",
                "finish_summary": "Debug flag enabled in config.json.",
            }),
        ]

        mock_primary = ScriptedModelClient(scripted_decisions)
        self.router.register_client("primary", mock_primary)

        loop = MasterAgentExecutionLoop(
            config=self.config,
            model_router=self.router,
            workspace_tools=self.tools,
            test_engine=self.engine,
        )

        trace = loop.run_loop(
            task_description="Enable debug flag in config.json",
            execute_tests=False,
        )

        self.assertEqual(trace.final_status, "SUCCESS")
        self.assertEqual(trace.tools_called, ["read_file", "patch_file"])

        # Verify file content on disk was actually patched
        patched_content = (self.temp_dir / "config.json").read_text(encoding="utf-8")
        self.assertIn('"debug": true', patched_content)

        # Verify observation from Step 1 was delivered in Step 2 prompt
        second_prompt = mock_primary.recorded_prompts[1]
        self.assertIn("debug", second_prompt)
        self.assertIn("false", second_prompt)

    def test_03_reviewer_escalation_and_remediation_application(self):
        """
        Master Agent requests review from Gemini 3.1 Pro High, receives required remediation,
        and applies changes.
        """
        (self.temp_dir / "auth.service.ts").write_text("const secret = 'insecure_default';\n", encoding="utf-8")

        scripted_primary_decisions = [
            # Step 1: Request specialist review for security change
            json.dumps({
                "thought": "This involves security auth changes. I must escalate to Pro Reviewer.",
                "action": "request_review",
                "reason": "Security sensitive credential change.",
            }),
            # Step 2: Conclude after remediation
            json.dumps({
                "thought": "Reviewer findings applied. Concluding task.",
                "action": "finish",
                "finish_summary": "Secured credentials per reviewer finding.",
            }),
        ]

        mock_primary = ScriptedModelClient(scripted_primary_decisions)
        self.router.register_client("primary", mock_primary)

        # Configure mock reviewer with structured required changes
        def reviewer_response(prompt: str) -> str:
            return json.dumps({
                "decision": "CHANGES_REQUIRED",
                "severity": "HIGH",
                "findings": ["Hardcoded secret violates security boundary."],
                "required_changes": [
                    {
                        "description": "Read secret from environment variable",
                        "target_file": "auth.service.ts",
                        "action": "patch",
                        "target_content": "const secret = 'insecure_default';",
                        "replacement_content": "const secret = process.env.JWT_SECRET;",
                    }
                ],
                "recommended_changes": [],
                "validation_requirements": ["Verify auth suite"],
            })

        mock_reviewer = MockSpecialistClient(
            is_available_flag=True,
            custom_response_generator=reviewer_response,
        )
        self.router.register_client("reviewer", mock_reviewer)

        loop = MasterAgentExecutionLoop(
            config=self.config,
            model_router=self.router,
            workspace_tools=self.tools,
            test_engine=self.engine,
        )

        trace = loop.run_loop(
            task_description="Secure auth service credential handling",
            execute_tests=False,
            should_escalate=True,
        )

        self.assertTrue(trace.reviewer_invoked)
        self.assertIsNotNone(trace.reviewer_feedback)
        self.assertEqual(len(trace.applied_remediations), 1)

        # Verify disk file was actually patched by remediation
        file_content = (self.temp_dir / "auth.service.ts").read_text(encoding="utf-8")
        self.assertIn("process.env.JWT_SECRET", file_content)

    def test_04_graceful_fallback_when_primary_model_unavailable(self):
        """
        When primary Gemini 3.8 Flash model is unavailable, execution loop
        executes safe fallback without faking model intelligence.
        """
        unavailable_primary = MockSpecialistClient(
            is_available_flag=False,
            unavailability_reason="GEMINI_API_KEY environment variable not configured.",
        )
        self.router.register_client("primary", unavailable_primary)

        (self.temp_dir / "README.md").write_text("# Test Docs\n", encoding="utf-8")

        loop = MasterAgentExecutionLoop(
            config=self.config,
            model_router=self.router,
            workspace_tools=self.tools,
            test_engine=self.engine,
        )

        trace = loop.run_loop(
            task_description="Inspect README documentation",
            changed_files=["README.md"],
            execute_tests=False,
        )

        self.assertEqual(trace.model_status, "UNAVAILABLE")
        self.assertEqual(trace.planning_mode, "FALLBACK_CLIENT_UNAVAILABLE")
        self.assertIn("GEMINI_API_KEY", trace.unavailability_reason)
        # Safe fallback read the file and checked environment
        self.assertIn("read_file", trace.tools_called)
        self.assertIn("run_command", trace.tools_called)


if __name__ == "__main__":
    unittest.main()

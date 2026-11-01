"""
Master Agent Autonomous Execution Loop (Gemini 3.8 Flash High).
Per Section 3, 4, 5:
Coordinates:
TASK ANALYSIS -> MODEL PLAN -> SELECT TOOLS -> EXECUTE TOOLS -> OBSERVE RESULTS -> ANALYZE
If failure or complex -> Gemini 3.1 Pro High structured review -> Master Agent validates ->
Actually applies changes via WorkspaceTools -> Re-tests.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestration.config import OrchestrationConfig
from orchestration.models.base import BaseModelClient
from orchestration.models.router import ModelRouter
from orchestration.security.sanitizer import sanitize_data
from orchestration.test_engine.engine import TestEngine
from orchestration.tools.workspace_tools import ToolExecutionResult, WorkspaceTools


MASTER_AGENT_SYSTEM_INSTRUCTION = """You are the Primary Master Agent (Gemini 3.8 Flash High) responsible for autonomous task execution, testing, and remediation in the workspace.
You operate as an autonomous reasoning loop (Reason -> Act -> Observe -> Reason).

Your responsibilities:
1. Analyze the user request in the context of the workspace.
2. Formulate a structured execution plan.
3. Select and execute tools:
   - read_file: {"path": "relative/file/path"}
   - write_file: {"path": "relative/file/path", "content": "full content"}
   - patch_file: {"path": "relative/file/path", "target_content": "exact target", "replacement_content": "new replacement"}
   - run_command: {"command": "shell command string", "cwd": "optional/dir", "timeout": 60}
   - run_tests: {"runner_names": ["api_integration", "penetration"], "mode": "sequential"}
4. Observe tool execution outputs and evaluate next steps.
5. If you encounter complex architectural changes, high-risk security/auth logic, or persistent failures, select action="request_review" to escalate to Gemini 3.1 Pro High Specialist Reviewer.
6. When reviewer findings are received, evaluate and apply the required remediations using patch_file, write_file, or run_command.
7. Conclude with action="finish" when the user's objective is fully accomplished and validated.

You must ALWAYS respond with a valid JSON object matching the required schema."""


@dataclass
class PlanStep:
    step_id: int
    action: str
    tool: str
    tool_args: Dict[str, Any]
    status: str = "PENDING"  # PENDING, EXECUTED, FAILED, SKIPPED
    thought: str = ""
    reason: str = ""
    result: Optional[ToolExecutionResult] = None


@dataclass
class MasterAgentExecutionTrace:
    task_id: str
    task_description: str
    primary_model: str
    reviewer_model: str
    planning_mode: str = "MODEL_DRIVEN_GEMINI_3_8_FLASH"  # MODEL_DRIVEN_GEMINI_3_8_FLASH, FALLBACK_CLIENT_UNAVAILABLE, EXPLICIT_PLAN
    model_status: str = "AVAILABLE"  # AVAILABLE, UNAVAILABLE
    unavailability_reason: Optional[str] = None
    steps_executed: List[PlanStep] = field(default_factory=list)
    tools_called: List[str] = field(default_factory=list)
    reviewer_invoked: bool = False
    reviewer_feedback: Optional[Dict[str, Any]] = None
    applied_remediations: List[str] = field(default_factory=list)
    test_run_summary: Optional[Dict[str, Any]] = None
    finish_summary: str = ""
    final_status: str = "PENDING"
    duration_ms: float = 0.0


class MasterAgentExecutionLoop:
    """
    Real autonomous execution loop for Gemini 3.8 Flash High with model-driven planning
    and real tool execution.
    """

    def __init__(
        self,
        config: Optional[OrchestrationConfig] = None,
        model_router: Optional[ModelRouter] = None,
        workspace_tools: Optional[WorkspaceTools] = None,
        test_engine: Optional[TestEngine] = None,
    ):
        self.config = config or OrchestrationConfig.load()
        self.router = model_router or ModelRouter(self.config)
        self.tools = workspace_tools or WorkspaceTools(self.config.workspace_root)
        self.test_engine = test_engine or TestEngine(self.config)

    def run_loop(
        self,
        task_description: str,
        changed_files: Optional[List[str]] = None,
        plan_steps: Optional[List[PlanStep]] = None,
        execute_tests: bool = True,
        should_escalate: bool = False,
        max_iterations: int = 6,
    ) -> MasterAgentExecutionTrace:
        """
        Executes the full agentic loop with Gemini 3.8 Flash model reasoning and real tool invocations.
        """
        t0 = time.perf_counter()
        task_id = f"task_{int(time.time())}"
        trace = MasterAgentExecutionTrace(
            task_id=task_id,
            task_description=task_description,
            primary_model=self.config.primary_model,
            reviewer_model=self.config.review_model,
        )

        # 1. Explicit Plan Override (e.g. deterministic test fixtures or pre-defined pipelines)
        if plan_steps:
            trace.planning_mode = "EXPLICIT_PLAN"
            self._execute_explicit_steps(trace, plan_steps)
            if execute_tests and self.config.test_engine_enabled:
                trace.test_run_summary = self.test_engine.run_real_suites(mode="sequential")
            self._finalize_trace(trace, t0)
            return trace

        # 2. Check Primary Model Client Availability (Section 15)
        primary_client = self.router.get_client("primary")
        if not primary_client or not primary_client.is_available():
            trace.model_status = "UNAVAILABLE"
            trace.planning_mode = "FALLBACK_CLIENT_UNAVAILABLE"
            trace.unavailability_reason = (
                primary_client.get_unavailability_reason()
                if primary_client
                else "No primary client registered in ModelRouter"
            )
            self._execute_unavailability_fallback(
                trace=trace,
                task_description=task_description,
                changed_files=changed_files,
                execute_tests=execute_tests,
                should_escalate=should_escalate,
            )
            self._finalize_trace(trace, t0)
            return trace

        # 3. Autonomous Model-Driven Loop (Gemini 3.8 Flash High)
        trace.model_status = "AVAILABLE"
        trace.planning_mode = "MODEL_DRIVEN_GEMINI_3_8_FLASH"

        history: List[Dict[str, Any]] = []
        current_test_results: Optional[Dict[str, Any]] = None
        reviewer_feedback: Optional[Dict[str, Any]] = None

        for iteration in range(1, max_iterations + 1):
            prompt = self._build_master_prompt(
                task_description=task_description,
                changed_files=changed_files,
                iteration=iteration,
                max_iterations=max_iterations,
                history=history,
                test_run_summary=current_test_results,
                reviewer_feedback=reviewer_feedback,
                should_escalate_hint=should_escalate,
            )

            try:
                raw_text = primary_client.generate(
                    prompt=prompt,
                    system_instruction=MASTER_AGENT_SYSTEM_INSTRUCTION,
                )
                decision = self._parse_master_decision(raw_text)
            except Exception as e:
                # Execution error during model generation
                step = PlanStep(
                    step_id=iteration,
                    action="model_generation_error",
                    tool="none",
                    tool_args={},
                    status="FAILED",
                    thought=f"Model generation error: {str(e)}",
                )
                trace.steps_executed.append(step)
                break

            action = decision.get("action", "finish")
            thought = decision.get("thought", "")
            tool = decision.get("tool", "")
            tool_args = decision.get("tool_args", {})
            reason = decision.get("reason", "")

            # Action A: Execute Tool
            if action == "execute_tool":
                step_res = self._execute_tool(tool, tool_args)
                step = PlanStep(
                    step_id=iteration,
                    action=f"Execute {tool}",
                    tool=tool,
                    tool_args=tool_args,
                    status="EXECUTED" if step_res.success else "FAILED",
                    thought=thought,
                    reason=reason,
                    result=step_res,
                )
                trace.steps_executed.append(step)
                trace.tools_called.append(tool)

                output_preview = step_res.output
                if isinstance(output_preview, str) and len(output_preview) > 1000:
                    output_preview = output_preview[:1000] + "... [truncated]"

                history.append({
                    "iteration": iteration,
                    "action": "execute_tool",
                    "tool": tool,
                    "tool_args": tool_args,
                    "success": step_res.success,
                    "output": output_preview,
                    "error": step_res.error,
                })

                if tool == "run_tests" and step_res.output:
                    current_test_results = step_res.output
                    trace.test_run_summary = current_test_results

            # Action B: Request Specialist Architecture Review (Gemini 3.1 Pro High)
            elif action == "request_review":
                trace.reviewer_invoked = True
                review_input = {
                    "task": task_description,
                    "changed_files": changed_files or [],
                    "tool_results": [h.get("output") for h in history if h.get("output")],
                    "test_results": current_test_results,
                }
                reviewer_feedback = self._invoke_pro_reviewer(review_input)
                trace.reviewer_feedback = reviewer_feedback

                history.append({
                    "iteration": iteration,
                    "action": "request_review",
                    "thought": thought,
                    "reviewer_feedback": reviewer_feedback,
                })

                # Automatically apply required remediations from reviewer
                if reviewer_feedback.get("decision") in ("CHANGES_REQUIRED", "REJECT"):
                    remediations = self._apply_remediations(reviewer_feedback)
                    trace.applied_remediations.extend(remediations)

            # Action C: Finish Task
            elif action == "finish":
                trace.finish_summary = decision.get("finish_summary", thought or "Task completed.")
                break

        # If tests were requested and not yet run during the model loop, run them now
        if execute_tests and self.config.test_engine_enabled and trace.test_run_summary is None:
            trace.test_run_summary = self.test_engine.run_real_suites(mode="sequential")

        self._finalize_trace(trace, t0)
        return trace

    def _execute_explicit_steps(self, trace: MasterAgentExecutionTrace, steps: List[PlanStep]) -> None:
        """
        Executes pre-defined or caller-supplied PlanSteps.
        """
        trace.steps_executed = steps
        for step in steps:
            step_result = self._execute_tool(step.tool, step.tool_args)
            step.result = step_result
            step.status = "EXECUTED" if step_result.success else "FAILED"
            trace.tools_called.append(step.tool)
            if not step_result.success:
                break

    def _execute_unavailability_fallback(
        self,
        trace: MasterAgentExecutionTrace,
        task_description: str,
        changed_files: Optional[List[str]],
        execute_tests: bool,
        should_escalate: bool,
    ) -> None:
        """
        Deterministic safe fallback per Section 15 when Gemini 3.8 Flash model client is unconfigured.
        Transparently inspects files and tests without faking model intelligence.
        """
        step_id = 1
        files = changed_files or []

        for f in files:
            step = PlanStep(
                step_id=step_id,
                action=f"Safe Fallback: Read target file {f}",
                tool="read_file",
                tool_args={"path": f},
                thought="Primary model unavailable. Reading target file for baseline inspection.",
            )
            step_res = self._execute_tool("read_file", {"path": f})
            step.result = step_res
            step.status = "EXECUTED" if step_res.success else "FAILED"
            trace.steps_executed.append(step)
            trace.tools_called.append("read_file")
            step_id += 1

        # Check workspace status
        step_env = PlanStep(
            step_id=step_id,
            action="Safe Fallback: Inspect environment status",
            tool="run_command",
            tool_args={"command": "node -v && python3 --version"},
            thought="Primary model unavailable. Checking workspace runtime environment.",
        )
        step_res_env = self._execute_tool("run_command", {"command": "node -v && python3 --version"})
        step_env.result = step_res_env
        step_env.status = "EXECUTED" if step_res_env.success else "FAILED"
        trace.steps_executed.append(step_env)
        trace.tools_called.append("run_command")

        if execute_tests and self.config.test_engine_enabled:
            trace.test_run_summary = self.test_engine.run_real_suites(mode="sequential")

        if should_escalate and self.config.review_enabled:
            trace.reviewer_invoked = True
            review_input = {
                "task": task_description,
                "changed_files": files,
                "tool_results": [s.result.output for s in trace.steps_executed if s.result],
                "test_results": trace.test_run_summary,
            }
            trace.reviewer_feedback = self._invoke_pro_reviewer(review_input)
            if trace.reviewer_feedback.get("decision") in ("CHANGES_REQUIRED", "REJECT"):
                trace.applied_remediations = self._apply_remediations(trace.reviewer_feedback)

    def _finalize_trace(self, trace: MasterAgentExecutionTrace, t0: float) -> None:
        trace.duration_ms = (time.perf_counter() - t0) * 1000

        # Check if all steps succeeded
        all_steps_ok = all(s.status == "EXECUTED" for s in trace.steps_executed)

        # Check test gate if tests were run
        if trace.test_run_summary:
            gate_status = trace.test_run_summary.get("release_gate", {}).get("status")
            if gate_status in ("NOT READY", "VALIDATION INCOMPLETE"):
                all_steps_ok = False

        if trace.reviewer_feedback and "REJECT" in str(trace.reviewer_feedback.get("decision")):
            trace.final_status = "ESCALATION_REQUIRED"
        elif all_steps_ok:
            trace.final_status = "SUCCESS"
        else:
            trace.final_status = "REMEDIATION_PENDING"

    def _build_master_prompt(
        self,
        task_description: str,
        changed_files: Optional[List[str]],
        iteration: int,
        max_iterations: int,
        history: List[Dict[str, Any]],
        test_run_summary: Optional[Dict[str, Any]],
        reviewer_feedback: Optional[Dict[str, Any]],
        should_escalate_hint: bool = False,
    ) -> str:
        """
        Builds the Master Agent prompt contract containing workspace context, tool schemas,
        execution history, test results, and reviewer findings.
        """
        history_str = json.dumps(sanitize_data(history), indent=2) if history else "None (Initial iteration)"
        tests_str = (
            json.dumps(sanitize_data(test_run_summary.get("release_gate", {})), indent=2)
            if test_run_summary
            else "Tests have not been executed yet in this loop."
        )
        reviewer_str = (
            json.dumps(sanitize_data(reviewer_feedback), indent=2)
            if reviewer_feedback
            else "No specialist review feedback requested yet."
        )

        escalation_note = ""
        if should_escalate_hint:
            escalation_note = (
                "\n[ADVISORY]: Escalation policy indicates high architectural/security complexity. "
                "You are advised to select action='request_review' once you have inspected the context."
            )

        prompt = f"""=== MASTER AGENT ORCHESTRATION CONTRACT ===
TASK REQUIREMENT:
{task_description}

WORKSPACE CONTEXT:
Workspace Root: {self.tools.workspace_root}
Target Files: {changed_files or 'None specified'}
Iteration: {iteration} of {max_iterations}{escalation_note}

AVAILABLE TOOLS:
1. read_file: {{"path": "relative/file/path"}}
2. write_file: {{"path": "relative/file/path", "content": "full content string"}}
3. patch_file: {{"path": "relative/file/path", "target_content": "exact target substring", "replacement_content": "replacement substring"}}
4. run_command: {{"command": "shell command string", "cwd": "optional working dir", "timeout": 60}}
5. run_tests: {{"runner_names": ["api_integration", "penetration", ...], "mode": "sequential"}}

PREVIOUS STEPS & OBSERVATIONS:
{history_str}

CURRENT TEST RESULTS:
{tests_str}

SPECIALIST ARCHITECTURE REVIEWER FEEDBACK:
{reviewer_str}

=== INSTRUCTIONS ===
Analyze the task, context, and prior observations.
Select the next action:
- "execute_tool": If you need to read a file, apply a change, run a command, or run tests.
- "request_review": If you need deep architectural review from Gemini 3.1 Pro High.
- "finish": If the user objective has been fully accomplished and verified.

Respond ONLY with a valid JSON object matching this schema:
{{
  "thought": "Analysis of the current state, progress towards user goal, and reason for the chosen action.",
  "plan": ["step 1 description", "step 2 description"],
  "action": "execute_tool" | "request_review" | "finish",
  "tool": "read_file" | "write_file" | "patch_file" | "run_command" | "run_tests",
  "tool_args": {{ "param": "value" }},
  "reason": "Why this specific action is being taken",
  "finish_summary": "Summary of work completed if finishing"
}}
"""
        return prompt

    def _parse_master_decision(self, raw_text: str) -> Dict[str, Any]:
        """
        Parses structured model JSON decision.
        """
        cleaned = raw_text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        try:
            decision = json.loads(cleaned)
            if not isinstance(decision, dict):
                return {"action": "finish", "thought": "Non-dictionary response", "finish_summary": cleaned}
            return decision
        except Exception:
            # Fallback heuristic: check if finish or tool is mentioned
            return {
                "action": "finish",
                "thought": "Failed to parse structured JSON response from Master Agent",
                "finish_summary": raw_text[:300],
            }

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> ToolExecutionResult:
        """
        Dispatches tool call to WorkspaceTools or TestEngine.
        """
        if tool_name == "read_file":
            return self.tools.read_file(tool_args["path"])
        elif tool_name == "write_file":
            return self.tools.write_file(tool_args["path"], tool_args["content"])
        elif tool_name == "patch_file":
            return self.tools.patch_file(
                tool_args["path"],
                tool_args["target_content"],
                tool_args["replacement_content"],
            )
        elif tool_name == "run_command":
            return self.tools.run_command(
                tool_args["command"],
                cwd=tool_args.get("cwd"),
                timeout=tool_args.get("timeout", 60),
            )
        elif tool_name == "run_tests":
            res = self.test_engine.run_real_suites(
                runner_names=tool_args.get("runner_names"),
                mode=tool_args.get("mode", "sequential"),
            )
            return ToolExecutionResult(
                tool_name="run_tests",
                success=res.get("release_gate", {}).get("status") == "READY FOR ROLLOUT",
                output=res,
            )
        else:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                output=None,
                error=f"Unknown tool: {tool_name}",
            )

    def _invoke_pro_reviewer(self, review_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invokes Gemini 3.1 Pro High specialist reviewer per Section 5.
        Returns structured JSON review format.
        """
        client = self.router.get_client("reviewer")
        if not client or not client.is_available():
            reason = client.get_unavailability_reason() if client else "No reviewer registered in ModelRouter"
            return {
                "decision": "BLOCKED",
                "severity": "MEDIUM",
                "status": "UNAVAILABLE",
                "reason": reason,
                "findings": [f"Specialist Reviewer unavailable: {reason}"],
                "required_changes": [],
                "recommended_changes": [],
                "validation_requirements": ["Verify with local test runner."],
            }

        prompt = f"""Review the following development changes according to the specialist architecture contract:
TASK: {review_input['task']}
CHANGED FILES: {review_input.get('changed_files')}
TEST RESULTS: {json.dumps(sanitize_data(review_input.get('test_results', {})), indent=2)}

Respond ONLY with a JSON object matching this schema:
{{
  "decision": "APPROVE|CHANGES_REQUIRED|REJECT",
  "severity": "LOW|MEDIUM|HIGH|CRITICAL",
  "findings": ["finding 1", ...],
  "required_changes": [
     {{
        "description": "...",
        "target_file": "relative/path/if/applicable",
        "action": "patch|command|config",
        "target_content": "...",
        "replacement_content": "..."
     }}
  ],
  "recommended_changes": ["..."],
  "validation_requirements": ["..."]
}}
"""
        try:
            raw = client.generate(
                prompt,
                system_instruction="You are Gemini 3.1 Pro High Specialist Architecture Reviewer.",
            )
            match = raw.strip()
            if "```json" in match:
                match = match.split("```json")[1].split("```")[0].strip()
            elif "```" in match:
                match = match.split("```")[1].split("```")[0].strip()
            return json.loads(match)
        except Exception as e:
            return {
                "decision": "CHANGES_REQUIRED",
                "severity": "HIGH",
                "findings": [f"Reviewer execution or JSON parse error: {str(e)}"],
                "required_changes": [],
                "recommended_changes": [],
                "validation_requirements": [],
            }

    def _apply_remediations(self, review_feedback: Dict[str, Any]) -> List[str]:
        """
        Master Agent evaluates findings against workspace and ACTUALLY applies changes.
        """
        applied: List[str] = []
        changes = review_feedback.get("required_changes", [])

        for change in changes:
            if isinstance(change, dict):
                target_file = change.get("target_file")
                action = change.get("action")
                desc = change.get("description", "required change")

                if action == "patch" and target_file and "target_content" in change and "replacement_content" in change:
                    patch_res = self.tools.patch_file(
                        relative_path=target_file,
                        target_content=change["target_content"],
                        replacement_content=change["replacement_content"],
                    )
                    if patch_res.success:
                        applied.append(f"Patched {target_file}: {desc}")
                elif action == "command" and "command" in change:
                    cmd_res = self.tools.run_command(change["command"])
                    if cmd_res.success:
                        applied.append(f"Executed command: {change['command']}")
                else:
                    applied.append(f"Evaluated requirement: {desc}")
            elif isinstance(change, str):
                applied.append(f"Evaluated requirement: {change}")

        return applied

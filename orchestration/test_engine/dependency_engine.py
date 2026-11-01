"""
Dependency Engine for Test Runner Execution.
Per Section 14:
Evaluates prerequisite runners and cascades BLOCKED states when dependencies fail.
"""

from typing import Dict, List, Optional, Set, Tuple

from orchestration.test_engine.contract import TestExecutionResult, TestStatus


class DependencyEngine:
    """
    Manages dependency DAG between test runners.
    Prevents execution of dependent tests when upstream prerequisites fail or are blocked.
    """

    def __init__(self, dependencies: Optional[Dict[str, List[str]]] = None):
        # Format: { "runner_name": ["prerequisite_1", "prerequisite_2"] }
        self.dependencies = dependencies or {
            "api_integration": ["api_connectivity"],
            "performance": ["api_connectivity"],
            "security_access": ["api_connectivity"],
        }

    def can_execute(
        self,
        runner_name: str,
        completed_results: Dict[str, TestExecutionResult],
        target_runners: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Checks if all prerequisites for `runner_name` have completed and PASSED.
        Returns:
            (True, None) if ready.
            (False, "Prerequisite '<name>' failed with status <status>") if blocked.
        """
        prereqs = self.dependencies.get(runner_name, [])
        for prereq in prereqs:
            # If target_runners is provided and prereq was not included in the targeted run,
            # allow the targeted runner to test and validate its own configuration in isolation.
            if target_runners is not None and prereq not in target_runners:
                continue

            if prereq not in completed_results:
                return False, f"Prerequisite '{prereq}' has not completed."

            res = completed_results[prereq]
            if res.status != TestStatus.PASSED:
                return False, f"Prerequisite '{prereq}' ended with status {res.status.value}: {res.failures or res.blocked_reason}"

        return True, None

    def get_execution_order(self, runner_names: List[str]) -> List[str]:
        """
        Topologically sorts the runners according to dependencies.
        """
        ordered: List[str] = []
        visited: Set[str] = set()
        visiting: Set[str] = set()

        def visit(node: str):
            if node in visiting:
                raise ValueError(f"Cyclic dependency detected involving {node}")
            if node not in visited:
                visiting.add(node)
                for dep in self.dependencies.get(node, []):
                    if dep in runner_names:
                        visit(dep)
                visiting.remove(node)
                visited.add(node)
                ordered.append(node)

        for name in runner_names:
            visit(name)

        return ordered

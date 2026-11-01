"""
Base Test Pillar Definition.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from orchestration.core_types import PillarSummary, TestPillar, TestResult


class BasePillar(ABC):
    """
    Abstract base class for each of the 6 test engine pillars.
    """

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    @property
    @abstractmethod
    def pillar_name(self) -> TestPillar:
        pass

    @abstractmethod
    def execute(self) -> PillarSummary:
        """
        Executes test suites for this pillar and returns a PillarSummary.
        """
        pass

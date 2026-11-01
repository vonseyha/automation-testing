"""
Base Model Client and Abstractions for Model Routing.
Per Section 13 & 15.
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseModelClient(ABC):
    """
    Abstract interface for model clients (Gemini API, Subagent bridge, Mock/Local).
    """

    def __init__(self, model_id: str, thinking_level: str = "high"):
        self.model_id = model_id
        self.thinking_level = thinking_level

    @abstractmethod
    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """
        Executes a model generation call and returns the text response.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Checks whether this model client can currently be invoked in this environment.
        """
        pass

    @abstractmethod
    def get_unavailability_reason(self) -> Optional[str]:
        """
        Returns a concise explanation if unavailable.
        """
        pass

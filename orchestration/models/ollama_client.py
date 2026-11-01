"""
Optional Ollama Local AI Client.
Connects only to a local Ollama runtime (default: http://localhost:11434).
Never transmits prompts or test data to hosted AI providers.
Never required for deterministic tests or the standard test workflow.
"""

import json
import os
import shutil
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from orchestration.models.base import BaseModelClient


class OllamaClient(BaseModelClient):
    """
    Local Ollama model client for optional AI-assisted evaluation.
    """

    def __init__(
        self,
        model_id: str = "llama3.2",
        thinking_level: str = "high",
        base_url: Optional[str] = None,
        timeout: float = 60.0,
    ):
        super().__init__(model_id=model_id, thinking_level=thinking_level)
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.timeout = timeout
        self._available: Optional[bool] = None
        self._unavail_reason: Optional[str] = None
        self._models: Optional[List[str]] = None

    def _check_availability(self) -> None:
        if self._available is not None:
            return

        ollama_bin = shutil.which("ollama")
        if not ollama_bin:
            self._available = False
            self._unavail_reason = "Ollama is not installed (not found in PATH)"
            return

        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                self._models = [m.get("name", "") for m in models]

                if not self._models:
                    self._available = False
                    self._unavail_reason = "Ollama is running but no models are downloaded locally"
                    return

                if self.model_id not in self._models and not any(self.model_id in m for m in self._models):
                    self._available = False
                    self._unavail_reason = (
                        f"Ollama is running but model '{self.model_id}' is not available locally. "
                        f"Available: {', '.join(self._models[:5])}"
                    )
                    return

                self._available = True
                self._unavail_reason = None

        except urllib.error.URLError:
            self._available = False
            self._unavail_reason = f"Ollama is installed but not running at {self.base_url}"
        except Exception as e:
            self._available = False
            self._unavail_reason = f"Ollama connectivity check failed: {e}"

    def is_available(self) -> bool:
        self._check_availability()
        return bool(self._available)

    def get_unavailability_reason(self) -> Optional[str]:
        self._check_availability()
        return self._unavail_reason

    def list_local_models(self) -> List[str]:
        self._check_availability()
        return self._models or []

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        if not self.is_available():
            return f"[UNAVAILABLE] {self._unavail_reason}"

        payload: Dict[str, Any] = {
            "model": self.model_id,
            "prompt": prompt,
            "stream": False,
        }
        if system_instruction:
            payload["system"] = system_instruction

        req_body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=req_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("response", "")
        except urllib.error.URLError as e:
            return f"[ERROR] Ollama request failed: {e}"
        except Exception as e:
            return f"[ERROR] Ollama generation error: {e}"

"""
Gemini API HTTP Client.
Direct REST API client using Python standard library (urllib.request).
Zero third-party dependencies required.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from orchestration.models.base import BaseModelClient


class GeminiApiClient(BaseModelClient):
    """
    Direct Gemini API client communicating over HTTPS REST endpoint.
    Uses GEMINI_API_KEY or GOOGLE_API_KEY environment variables.
    """

    def __init__(
        self,
        model_id: str = "gemini-3.1-pro-preview",
        thinking_level: str = "high",
        api_key: Optional[str] = None,
        endpoint: str = "https://generativelanguage.googleapis.com/v1beta",
    ):
        super().__init__(model_id=model_id, thinking_level=thinking_level)
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.endpoint = endpoint

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def get_unavailability_reason(self) -> Optional[str]:
        if not self.api_key:
            return "GEMINI_API_KEY / GOOGLE_API_KEY environment variable is not configured."
        return None

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        if not self.is_available():
            raise RuntimeError(f"Gemini API client unavailable: {self.get_unavailability_reason()}")

        # Build payload according to Gemini REST API specification
        url = f"{self.endpoint}/models/{self.model_id}:generateContent?key={self.api_key}"

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "topP": 0.95,
            },
        }

        # Thinking config if supported
        if self.thinking_level:
            payload["generationConfig"]["thinkingConfig"] = {
                "thinkingBudget": 4096 if self.thinking_level == "high" else 2048
            }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)

                # Extract generated text from candidates
                candidates = res_json.get("candidates", [])
                if not candidates:
                    return ""
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join(part.get("text", "") for part in parts)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(f"Gemini API HTTP Error {e.code}: {e.reason} - {error_body}") from e
        except Exception as e:
            raise RuntimeError(f"Gemini API call failed: {str(e)}") from e

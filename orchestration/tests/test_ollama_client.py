"""
Tests for the optional Ollama local AI client.
"""

import unittest
from unittest.mock import patch

from orchestration.models.ollama_client import OllamaClient


class TestOllamaClient(unittest.TestCase):
    def test_unavailable_when_not_installed(self):
        with patch("orchestration.models.ollama_client.shutil.which", return_value=None):
            client = OllamaClient()
            self.assertFalse(client.is_available())
            reason = client.get_unavailability_reason()
            self.assertIn("not installed", reason)

    def test_generate_returns_unavailable_when_not_installed(self):
        with patch("orchestration.models.ollama_client.shutil.which", return_value=None):
            client = OllamaClient()
            result = client.generate("test prompt")
            self.assertIn("[UNAVAILABLE]", result)

    def test_list_models_empty_when_not_installed(self):
        with patch("orchestration.models.ollama_client.shutil.which", return_value=None):
            client = OllamaClient()
            models = client.list_local_models()
            self.assertEqual(models, [])

    def test_default_base_url(self):
        client = OllamaClient()
        self.assertEqual(client.base_url, "http://localhost:11434")

    def test_custom_model_and_url(self):
        client = OllamaClient(model_id="mistral", base_url="http://custom:1234")
        self.assertEqual(client.model_id, "mistral")
        self.assertEqual(client.base_url, "http://custom:1234")

    def test_never_required_for_standard_workflow(self):
        with patch("orchestration.models.ollama_client.shutil.which", return_value=None):
            client = OllamaClient()
            self.assertFalse(client.is_available())
            reason = client.get_unavailability_reason()
            self.assertIsNotNone(reason)


if __name__ == "__main__":
    unittest.main()

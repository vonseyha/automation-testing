"""
Unit tests for OrchestrationConfig.
"""

import os
import unittest

from orchestration.config import OrchestrationConfig
from orchestration.core_types import ThinkingLevel


class TestOrchestrationConfig(unittest.TestCase):
    def test_default_config(self):
        config = OrchestrationConfig.load()
        self.assertEqual(config.primary_model, "gemini-3.8-flash")
        self.assertEqual(config.primary_thinking_level, ThinkingLevel.HIGH)
        self.assertEqual(config.review_model, "gemini-3.1-pro-preview")
        self.assertEqual(config.review_thinking_level, ThinkingLevel.HIGH)
        self.assertTrue(config.review_enabled)
        self.assertEqual(config.review_max_iterations, 3)
        self.assertTrue(config.test_engine_enabled)
        self.assertEqual(config.backend_workspace.name, "topautokh-api")
        self.assertEqual(config.api_health_endpoint, "/health")
        self.assertEqual(config.api_base_url, "http://localhost:3000")

    def test_override_config(self):
        config = OrchestrationConfig.load(
            primary_model="custom-flash",
            review_max_iterations=5,
            review_enabled=False,
            api_health_endpoint="/health",
            api_base_url="http://localhost:8080",
        )
        self.assertEqual(config.primary_model, "custom-flash")
        self.assertEqual(config.review_max_iterations, 5)
        self.assertFalse(config.review_enabled)
        self.assertEqual(config.api_health_endpoint, "/health")
        self.assertEqual(config.api_base_url, "http://localhost:8080")

    def test_to_dict(self):
        config = OrchestrationConfig.load()
        d = config.to_dict()
        self.assertIn("PRIMARY_MODEL", d)
        self.assertIn("REVIEW_MODEL", d)
        self.assertEqual(d["PRIMARY_THINKING_LEVEL"], "high")
        self.assertIn("BACKEND_WORKSPACE", d)
        self.assertIn("API_HEALTH_ENDPOINT", d)
        self.assertIn("API_BASE_URL", d)
        self.assertTrue(d["BACKEND_WORKSPACE"].endswith("topautokh-api"))

    def test_backend_workspace_does_not_use_cluster(self):
        config = OrchestrationConfig.load()
        self.assertNotIn("topauto-api-cluster", str(config.backend_workspace))
        self.assertTrue(str(config.backend_workspace).endswith("topautokh-api"))


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for Safety & Secrets Sanitizer.
"""

import unittest

from orchestration.security.sanitizer import sanitize_data, sanitize_text


class TestSanitizer(unittest.TestCase):
    def test_sanitize_gemini_key(self):
        text = "Connecting with key AIzaSyD123456789012345678901234567890123 to Gemini."
        sanitized = sanitize_text(text)
        self.assertNotIn("AIzaSy", sanitized)
        self.assertIn("[REDACTED_GEMINI_API_KEY]", sanitized)

    def test_sanitize_jwt_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozGz"
        sanitized = sanitize_text(text)
        self.assertNotIn("eyJhbGciOi", sanitized)
        self.assertIn("[REDACTED_JWT_TOKEN]", sanitized)

    def test_sanitize_db_password(self):
        text = "mongodb://admin:supersecret123@localhost:27017/topauto?replicaSet=rs0"
        sanitized = sanitize_text(text)
        self.assertNotIn("supersecret123", sanitized)
        self.assertIn("[REDACTED_PASSWORD]", sanitized)

    def test_sanitize_dict_recursive(self):
        payload = {
            "user": "test-user",
            "password": "my_clear_password",
            "metadata": {
                "apiKey": "AIzaSyD123456789012345678901234567890123",
                "notes": "safe text",
            },
        }
        sanitized = sanitize_data(payload)
        self.assertEqual(sanitized["password"], "[REDACTED_SENSITIVE_FIELD]")
        self.assertNotIn("AIzaSy", str(sanitized))
        self.assertEqual(sanitized["metadata"]["notes"], "safe text")


if __name__ == "__main__":
    unittest.main()

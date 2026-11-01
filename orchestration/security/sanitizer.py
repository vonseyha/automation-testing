"""
Safety & Secrets Sanitizer for Review Requests and Audits.
Per Section 6 & 16:
Redacts credentials, secrets, tokens, private keys, database passwords, and private cookies
before any context is sent to the specialist reviewer or written to audit logs.
"""

import re
from typing import Any, Dict, List, Union

# Compiled regex patterns for detecting secrets
PATTERNS = [
    # Google / Gemini API Keys (e.g. AIzaSy...)
    (re.compile(r"AIza[0-9A-Za-z-_]{20,}", re.IGNORECASE), "[REDACTED_GEMINI_API_KEY]"),
    # AWS Access Keys
    (re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    # Generic API Keys / Tokens in code or config
    (
        re.compile(r"""(?i)(api[_-]?key|secret|token|auth[_-]?token|client[_-]?secret)\s*[:=]\s*['"][a-zA-Z0-9_\-\.]{8,}['"]"""),
        r'\1: "[REDACTED_SECRET]"',
    ),
    # JWT Tokens (e.g. eyJhbGciOi...)
    (re.compile(r"eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]+"), "[REDACTED_JWT_TOKEN]"),
    # Bearer Tokens
    (re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{15,}"), "Bearer [REDACTED_BEARER_TOKEN]"),
    # MongoDB / Database Connection Strings with Passwords
    (
        re.compile(r"""(mongodb(?:\+srv)?:\/\/[^:]+:)([^@]+)(@)""", re.IGNORECASE),
        r"\1[REDACTED_PASSWORD]\3",
    ),
    (
        re.compile(r"""((?:postgres|mysql|redis):\/\/[^:]+:)([^@]+)(@)""", re.IGNORECASE),
        r"\1[REDACTED_PASSWORD]\3",
    ),
    # Private Keys (RSA, EC, OPENSSH)
    (
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # Passwords in JSON/Objects (e.g. "password": "xyz")
    (
        re.compile(r"""(?i)(["']?password["']?\s*:\s*["'])(?:(?=(\\?))\2.)*?(["'])"""),
        r'\1[REDACTED_PASSWORD]\3',
    ),
    # HMAC secrets (e.g. secret = 'default_hmac_secret_for_dev')
    (
        re.compile(r"""(?i)(hmac[_-]?secret|jwt[_-]?secret)\s*=\s*['"][^'"]+['"]"""),
        r'\1 = "[REDACTED_SECRET]"',
    ),
    # Cookies / Sessions
    (
        re.compile(r"""(?i)(session[_-]?id|connect\.sid)\s*=\s*[a-zA-Z0-9_\-\.]{10,}"""),
        r"\1=[REDACTED_SESSION]",
    ),
]


def sanitize_text(text: str) -> str:
    """
    Sanitizes plain text or code strings, replacing all recognized sensitive tokens with redaction tags.
    """
    if not isinstance(text, str):
        return text

    sanitized = text
    for pattern, replacement in PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def sanitize_data(data: Union[Dict[str, Any], List[Any], str, Any]) -> Any:
    """
    Recursively traverses dictionaries, lists, and strings to sanitize sensitive information.
    """
    if isinstance(data, str):
        return sanitize_text(data)
    elif isinstance(data, dict):
        sanitized_dict = {}
        for k, v in data.items():
            # Check if the key itself implies a secret
            if re.search(r"(?i)(password|secret|token|api[_-]?key|private[_-]?key)", k):
                sanitized_dict[k] = "[REDACTED_SENSITIVE_FIELD]"
            else:
                sanitized_dict[k] = sanitize_data(v)
        return sanitized_dict
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    return data

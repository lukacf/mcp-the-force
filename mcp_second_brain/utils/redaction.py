"""Secret redaction utilities for memory storage."""

import re
from typing import Dict, Any

# Common patterns for secrets
SECRET_PATTERNS = [
    # API Keys
    (
        r'(api[_-]?key|apikey|access[_-]?key)[\s:=]+[\'""]?([a-zA-Z0-9_\-]{20,})[\'""]?',
        r"\1=REDACTED",
    ),
    (
        r'(secret[_-]?key|secret)[\s:=]+[\'""]?([a-zA-Z0-9_\-]{20,})[\'""]?',
        r"\1=REDACTED",
    ),
    # AWS
    (r"(AKIA[A-Z0-9]{16})", "AWS_ACCESS_KEY_REDACTED"),
    (
        r'(aws[_-]?secret[_-]?access[_-]?key)[\s:=]+[\'""]?([a-zA-Z0-9/+=]{40})[\'""]?',
        r"\1=REDACTED",
    ),
    # GitHub tokens
    (r"(ghp_[a-zA-Z0-9]{36})", "GITHUB_TOKEN_REDACTED"),
    (r"(gho_[a-zA-Z0-9]{36})", "GITHUB_OAUTH_REDACTED"),
    # Generic tokens
    (r'(token|bearer)[\s:=]+[\'""]?([a-zA-Z0-9_\-\.]{20,})[\'""]?', r"\1=REDACTED"),
    # Database URLs
    (r"(postgres|mysql|mongodb)://[^:]+:([^@]+)@", r"\1://user:REDACTED@"),
    # Private keys (multiline)
    (
        r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----\nREDACTED\n-----END PRIVATE KEY-----",
    ),
]


def redact_secrets(text: str) -> str:
    """Redact common secret patterns from text.

    Args:
        text: Text that may contain secrets

    Returns:
        Text with secrets replaced by REDACTED markers
    """
    if not text:
        return text

    result = text
    for pattern, replacement in SECRET_PATTERNS:
        result = re.sub(
            pattern, replacement, result, flags=re.IGNORECASE | re.MULTILINE
        )

    return result


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redact secrets from a dictionary.

    Args:
        data: Dictionary that may contain secrets in string values

    Returns:
        Dictionary with secrets redacted
    """
    if not isinstance(data, dict):
        return data

    result: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = redact_secrets(value)
        elif isinstance(value, dict):
            result[key] = redact_dict(value)
        elif isinstance(value, list):
            result[key] = [
                redact_secrets(item)
                if isinstance(item, str)
                else redact_dict(item)
                if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            result[key] = value

    return result

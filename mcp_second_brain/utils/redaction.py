"""Secret redaction utilities for memory storage."""

import re
from typing import Dict, Any


# Common patterns for secrets - compiled for efficiency
SECRET_PATTERNS: list[re.Pattern] = [
    # OpenAI keys (sk-), Anthropic keys (sk-ant-)
    re.compile(r"sk-[a-zA-Z0-9-]{16,}"),
    # GitHub tokens
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"github_pat_[A-Za-z0-9]{22,}"),
    # AWS keys
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # Generic patterns for key=value or key: value
    # This pattern uses a capturing group for the key part.
    re.compile(
        r"(\b(api_key|apikey|api-key|token|access_token|password|pass|pwd|secret|auth_token)\b)\s*[:=]\s*['\"]?[^'\"\\\s]{8,}[^'\"\\\s]*['\"]?",
        re.IGNORECASE,
    ),
]

DB_URL_PATTERN = re.compile(r"([a-zA-Z0-9+]+://[^:]+:)([^@]+)(@)")


def redact_secrets(text: str) -> str:
    """Redact common secret patterns from text.

    Args:
        text: Text that may contain secrets

    Returns:
        Text with secrets replaced by REDACTED markers
    """
    if not text:
        return text

    # Apply specific patterns that match the whole secret
    for pattern in SECRET_PATTERNS[:-1]:
        text = pattern.sub("***", text)

    # Apply generic key=value pattern, preserving the key but always using =
    def replace_key_value(match):
        key = match.group(1)
        return f"{key}=***"

    text = SECRET_PATTERNS[-1].sub(replace_key_value, text)

    # Special case for database URLs - redact passwords
    text = DB_URL_PATTERN.sub(r"\1***\3", text)

    return text


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

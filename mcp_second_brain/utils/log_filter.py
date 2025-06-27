import logging
import os
import re

class SecretRedactionFilter(logging.Filter):
    """Filter that redacts secrets from log records."""

    SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9]+")

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = self.SECRET_PATTERN.sub("[REDACTED]", message)
        for name, value in os.environ.items():
            if (name.upper().endswith("_KEY") or name.upper().endswith("_SECRET")) and value:
                redacted = redacted.replace(value, "[REDACTED]")
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True

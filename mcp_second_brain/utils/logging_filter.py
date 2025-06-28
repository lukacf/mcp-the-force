"""Logging filter for automatic secret redaction."""

import logging
from .redaction import redact_secrets


class RedactionFilter(logging.Filter):
    """Automatically redact secrets from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records to redact secrets.

        Args:
            record: The log record to filter

        Returns:
            True (always allows the record through after redaction)
        """
        # Redact the main message
        if hasattr(record, "msg"):
            record.msg = redact_secrets(str(record.msg))

        # Redact the arguments if present
        if hasattr(record, "args") and record.args:
            if isinstance(record.args, dict):
                # For dict-style formatting
                record.args = {
                    k: redact_secrets(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            else:
                # For tuple-style formatting
                record.args = tuple(
                    redact_secrets(str(arg)) if isinstance(arg, str) else arg
                    for arg in record.args
                )

        return True

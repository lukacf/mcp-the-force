"""Logging filter for automatic secret redaction."""

import logging
from .redaction import redact_secrets


class RedactionFilter(logging.Filter):
    """Automatically redact secrets from log messages."""

    MAX_REDACTION_SIZE = 8 * 1024  # 8KB - skip expensive regex on large messages

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records to redact secrets.

        Args:
            record: The log record to filter

        Returns:
            True (always allows the record through after redaction)
        """
        # Skip expensive regex processing on very large messages
        # The handler will truncate them later anyway
        if hasattr(record, "msg") and len(str(record.msg)) > self.MAX_REDACTION_SIZE:
            return True

        # Redact the main message
        if hasattr(record, "msg"):
            record.msg = redact_secrets(str(record.msg))

        # Redact the arguments if present
        if hasattr(record, "args") and record.args:
            if isinstance(record.args, dict):
                # For dict-style formatting
                record.args = {
                    k: redact_secrets(str(v))
                    if isinstance(v, str) and len(v) <= self.MAX_REDACTION_SIZE
                    else v
                    for k, v in record.args.items()
                }
            else:
                # For tuple-style formatting
                record.args = tuple(
                    redact_secrets(str(arg))
                    if isinstance(arg, str) and len(str(arg)) <= self.MAX_REDACTION_SIZE
                    else arg
                    for arg in record.args
                )

        return True

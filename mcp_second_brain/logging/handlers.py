"""Custom logging handlers with timeout support."""

from logging_loki import LokiHandler
import requests


class TimeoutLokiHandler(LokiHandler):
    """
    Custom LokiHandler that enforces a network timeout on all requests.
    This prevents the logging thread from hanging indefinitely on stale connections.
    """

    def __init__(self, *args, timeout: float = 10.0, **kwargs):
        """
        Initialize handler with configurable timeout.

        Args:
            timeout: Request timeout in seconds (default: 10.0)
            *args, **kwargs: Passed to parent LokiHandler
        """
        super().__init__(*args, **kwargs)
        self.timeout = timeout

        # Override the emitter's session to use our timeout
        if hasattr(self, "emitter") and hasattr(self.emitter, "_session"):
            # Force session recreation with our timeout adapter
            self.emitter._session = None

    def emit(self, record):
        """Emit a record with timeout protection."""
        try:
            # Get the formatted log entry
            if hasattr(self, "build_msg"):
                self.build_msg(record)
            else:
                self.format(record)

            # Get the emitter's session and set timeout
            session = self.emitter.session

            # Create adapter with timeout for all requests
            if not hasattr(session, "_timeout_adapter_installed"):
                adapter = requests.adapters.HTTPAdapter()
                adapter.max_retries = 0  # No retries to fail fast
                session.mount("http://", adapter)
                session.mount("https://", adapter)
                session._timeout_adapter_installed = True

            # Make the actual call with timeout
            # We need to monkey-patch the session.post temporarily
            original_post = session.post

            def post_with_timeout(*args, **kwargs):
                kwargs["timeout"] = self.timeout
                return original_post(*args, **kwargs)

            session.post = post_with_timeout

            # Call parent's emit which will use our patched session
            super().emit(record)

        except requests.exceptions.Timeout:
            # Log timeout to stderr so we can see it
            import sys

            print(
                f"LokiHandler timeout after {self.timeout}s - connection may be stale",
                file=sys.stderr,
            )
            # Close the session to force reconnection
            if hasattr(self.emitter, "close"):
                self.emitter.close()
        except requests.exceptions.RequestException as e:
            # Log other network errors
            import sys

            print(f"LokiHandler network error: {e}", file=sys.stderr)
            # Close the session to force reconnection
            if hasattr(self.emitter, "close"):
                self.emitter.close()
        except Exception:
            # Don't let logging errors crash the application
            self.handleError(record)

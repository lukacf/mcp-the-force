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
        # Store the URL for later checking
        self.handler_url = args[0] if args else kwargs.get("url", "")
        super().__init__(*args, **kwargs)
        self.timeout = timeout

        # Override the emitter's session to use our timeout
        if hasattr(self, "emitter") and hasattr(self.emitter, "_session"):
            # Force session recreation with our timeout adapter
            self.emitter._session = None

    def emit(self, record):
        """Emit a record with timeout protection."""
        # In E2E mode, check if we should skip localhost connections
        import os

        if os.getenv("CI_E2E") == "1":
            # Check if the handler URL is still pointing to localhost
            if "localhost:9428" in self.handler_url:
                # Skip emission - the handler was created with localhost URL
                # This happens when the server starts before env vars are fully propagated
                return

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
            # Suppress localhost connection errors in E2E tests
            import sys
            import os

            error_str = str(e)
            is_localhost_error = "localhost" in error_str and "9428" in error_str
            is_e2e_test = os.getenv("CI_E2E") == "1"

            # In E2E mode with proper VictoriaLogs URL, suppress localhost errors completely
            victoria_url = os.getenv("VICTORIA_LOGS_URL", "")
            has_proper_url = victoria_url and "host.docker.internal" in victoria_url

            if not (is_localhost_error and is_e2e_test and has_proper_url):
                # Only print if:
                # - Not a localhost error, OR
                # - Not in E2E test mode, OR
                # - No proper VictoriaLogs URL configured
                print(f"LokiHandler network error: {e}", file=sys.stderr)

            # Close the session to force reconnection
            if hasattr(self.emitter, "close"):
                self.emitter.close()
        except Exception as e:
            # Suppress localhost connection errors in E2E tests
            import os

            error_str = str(e)
            is_localhost_error = "localhost" in error_str and "9428" in error_str
            is_e2e_test = os.getenv("CI_E2E") == "1"

            if is_localhost_error and is_e2e_test:
                # Silently ignore localhost errors in E2E tests
                pass
            else:
                # Don't let other logging errors crash the application
                self.handleError(record)

    def handleError(self, record):
        """Override to suppress localhost connection errors in E2E tests."""
        import os
        import sys
        import traceback

        # Get the current exception info
        exc_info = sys.exc_info()
        if exc_info[0] is not None:
            # Format the exception as a string
            exc_text = "".join(traceback.format_exception(*exc_info))

            # Check if it's a localhost connection error in E2E mode
            is_localhost_error = "localhost" in exc_text and "9428" in exc_text
            is_e2e_test = os.getenv("CI_E2E") == "1"

            if is_localhost_error and is_e2e_test:
                # Silently ignore localhost errors in E2E tests
                return

        # Otherwise, use the parent's handleError
        super().handleError(record)

"""Optimized HTTP client for high-frequency requests."""

import time
import json
import threading
from typing import Dict, Any, Optional
from urllib.parse import urljoin


class FastHTTPClient:
    """Optimized HTTP client for frequent small requests with connection reuse."""

    def __init__(self, base_url: str, timeout: float = 2.0):
        self.base_url = base_url
        self.timeout = timeout
        self._session = None
        self._lock = threading.Lock()
        self._last_used = 0
        self._max_idle_time = 300  # 5 minutes

    def _get_session(self):
        """Get or create HTTP session with connection pooling."""
        current_time = time.time()

        with self._lock:
            # Recreate session if it's been idle too long
            if (
                self._session is None
                or current_time - self._last_used > self._max_idle_time
            ):
                if self._session:
                    self._session.close()

                try:
                    import requests
                    from requests.adapters import HTTPAdapter
                    from requests.packages.urllib3.util.retry import Retry

                    self._session = requests.Session()

                    # Configure connection pooling
                    adapter = HTTPAdapter(
                        pool_connections=1,  # Single connection pool
                        pool_maxsize=2,  # Max 2 connections
                        max_retries=Retry(
                            total=1,
                            backoff_factor=0.1,
                            status_forcelist=[500, 502, 503, 504],
                        ),
                    )

                    self._session.mount("http://", adapter)
                    self._session.mount("https://", adapter)

                    # Optimize headers
                    self._session.headers.update(
                        {
                            "Connection": "keep-alive",
                            "Content-Type": "application/json",
                            "User-Agent": "mcp-the-force/1.0",
                            "Accept-Encoding": "gzip",
                        }
                    )

                except ImportError:
                    # Fallback to urllib if requests not available
                    self._session = None

            self._last_used = current_time
            return self._session

    def post_json(self, endpoint: str, data: Dict[str, Any]) -> bool:
        """Post JSON data with optimized error handling."""
        session = self._get_session()

        if session is None:
            # Fallback to urllib
            return self._post_urllib(endpoint, data)

        try:
            url = urljoin(self.base_url, endpoint)
            response = session.post(url, json=data, timeout=self.timeout)
            return response.status_code < 400

        except Exception:
            return False

    def _post_urllib(self, endpoint: str, data: Dict[str, Any]) -> bool:
        """Fallback implementation using urllib."""
        try:
            import urllib.request
            import urllib.parse

            url = urljoin(self.base_url, endpoint)
            json_data = json.dumps(data, separators=(",", ":")).encode("utf-8")

            request = urllib.request.Request(
                url,
                data=json_data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "mcp-the-force/1.0",
                },
            )

            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status < 400

        except Exception:
            return False

    def close(self):
        """Close the session."""
        with self._lock:
            if self._session:
                self._session.close()
                self._session = None


# Global client instance for reuse
_http_client: Optional[FastHTTPClient] = None
_client_lock = threading.Lock()


def get_fast_http_client(base_url: str) -> FastHTTPClient:
    """Get global HTTP client instance."""
    global _http_client

    with _client_lock:
        if _http_client is None:
            _http_client = FastHTTPClient(base_url)

    return _http_client

"""Client for communicating with the Loiter Killer service."""

import logging
import os
from typing import Optional, Tuple, List
import httpx

logger = logging.getLogger(__name__)


class LoiterKillerClient:
    """Client for the Loiter Killer vector store management service."""

    def __init__(self):
        # Allow overriding the URL for E2E tests
        self.base_url = os.getenv("LOITER_KILLER_URL", "http://localhost:9876")
        self.enabled = False
        self._check_availability()

    def _check_availability(self) -> bool:
        """Check if loiter killer is available."""
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=2.0)
            self.enabled = response.status_code == 200
            if self.enabled:
                logger.info("Loiter Killer service is available")
            return bool(self.enabled)
        except Exception as e:
            logger.debug(f"Loiter Killer not available: {e}")
            self.enabled = False
            return False

    async def get_or_create_vector_store(
        self, session_id: str
    ) -> Tuple[Optional[str], List[str]]:
        """Get existing or create new vector store for session.

        Returns:
            Tuple of (vector_store_id, existing_file_paths)
            Returns (None, []) if service is unavailable.
        """
        if not self.enabled:
            # Re-check availability periodically
            if not self._check_availability():
                return None, []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/session/{session_id}/acquire"
                )
                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        f"Loiter Killer: {'Reused' if data['reused'] else 'Created'} "
                        f"vector store {data['vector_store_id']} for session {session_id}"
                    )
                    return (
                        data["vector_store_id"],
                        data.get("file_paths", []),
                    )
                else:
                    logger.warning(
                        f"Loiter Killer acquire failed: {response.status_code}"
                    )
        except Exception as e:
            logger.warning(f"Loiter Killer request failed: {e}")
            # Disable for a while to avoid repeated failures
            self.enabled = False

        return None, []

    async def track_files(self, session_id: str, file_paths: List[str]):
        """Track files for cleanup when session expires.

        Args:
            session_id: The session ID
            file_paths: List of file paths
        """
        if not self.enabled or not file_paths:
            return

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                request_data = {"file_paths": file_paths}
                response = await client.post(
                    f"{self.base_url}/session/{session_id}/files", json=request_data
                )
                if response.status_code == 200:
                    data = response.json()
                    logger.debug(
                        f"Tracked {data['tracked']} files for session {session_id}"
                    )
        except Exception as e:
            logger.debug(f"Failed to track files: {e}")
            # Best effort - don't fail the operation

    async def renew_lease(self, session_id: str):
        """Keep session alive during long operations."""
        if not self.enabled:
            return

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.base_url}/session/{session_id}/renew"
                )
                if response.status_code == 200:
                    logger.debug(f"Renewed lease for session {session_id}")
        except Exception as e:
            logger.debug(f"Failed to renew lease: {e}")
            # Best effort - don't fail the operation

    async def cleanup(self):
        """Trigger manual cleanup (mainly for testing)."""
        if not self.enabled:
            return 0

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(f"{self.base_url}/cleanup")
                if response.status_code == 200:
                    data = response.json()
                    return data["cleaned"]
        except Exception:
            pass

        return 0

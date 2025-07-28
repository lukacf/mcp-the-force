"""Client for communicating with the Loiter Killer service."""

import logging
from typing import Optional, Tuple, List
import httpx

logger = logging.getLogger(__name__)


class LoiterKillerClient:
    """Client for the Loiter Killer vector store management service."""

    def __init__(self):
        # Get settings for configuration
        from ..config import get_settings

        settings = get_settings()

        self.base_url = settings.services.loiter_killer_url
        self.enabled = False

        # Check if we're in mock mode
        if settings.dev.adapter_mock:
            # In mock mode, pretend loiter killer is not available
            logger.info("[LOITER_KILLER] Mock mode - service disabled")
            self.enabled = False
        else:
            self._check_availability()

    def _check_availability(self) -> bool:
        """Check if loiter killer is available."""
        logger.info(f"[LOITER_KILLER] Checking availability at {self.base_url}/health")
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=2.0)
            self.enabled = response.status_code == 200
            if self.enabled:
                logger.info(f"[LOITER_KILLER] Service is available at {self.base_url}")
            else:
                logger.warning(
                    f"[LOITER_KILLER] Service returned status {response.status_code}"
                )
            return bool(self.enabled)
        except Exception as e:
            logger.warning(
                f"[LOITER_KILLER] Service not available at {self.base_url}: {e}"
            )
            self.enabled = False
            return False

    async def get_or_create_vector_store(
        self, session_id: str, protected: bool = False
    ) -> Tuple[Optional[str], List[str]]:
        """Get existing or create new vector store for session.

        Args:
            session_id: The session ID
            protected: Whether this is a protected store (e.g., project history)

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
                request_data = {"protected": protected}
                response = await client.post(
                    f"{self.base_url}/session/{session_id}/acquire", json=request_data
                )
                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        f"Loiter Killer: {'Reused' if data['reused'] else 'Created'} "
                        f"{'protected ' if protected else ''}"
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

    async def register_existing_store(
        self, session_id: str, vector_store_id: str, protected: bool = True
    ) -> bool:
        """Register an already-created vector store with LoiterKiller.

        Args:
            session_id: The session ID to use for tracking
            vector_store_id: The existing OpenAI vector store ID
            protected: Whether this is a protected store (default True for project history)

        Returns:
            True if successfully registered, False otherwise
        """
        if not self.enabled:
            logger.debug("LoiterKiller not enabled, skipping registration")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                request_data = {
                    "vector_store_id": vector_store_id,
                    "protected": protected,
                }
                response = await client.post(
                    f"{self.base_url}/session/{session_id}/register", json=request_data
                )
                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        f"Registered existing store {vector_store_id} with LoiterKiller "
                        f"for session {session_id} (status: {data['status']})"
                    )
                    return True
                else:
                    logger.warning(
                        f"Failed to register store: {response.status_code} - {response.text}"
                    )
                    return False
        except Exception as e:
            logger.warning(f"Failed to register existing store: {e}")
            return False

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

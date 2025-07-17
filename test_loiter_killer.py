#!/usr/bin/env python3
"""
Test suite for Loiter Killer service using TDD approach.
"""

import pytest
import httpx
import time
import os
import subprocess
import sys


@pytest.fixture(scope="session")
def loiter_killer_service():
    """Start the Loiter Killer service for testing."""
    # Clean up any existing test database
    if os.path.exists("loiter_killer.db"):
        os.remove("loiter_killer.db")

    # Set test environment
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = "test-key"
    env["TEST_MODE"] = "true"

    # Start the service
    process = subprocess.Popen(
        [sys.executable, "loiter_killer.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    # Wait for service to start
    time.sleep(2)

    yield

    # Stop the service
    process.terminate()
    process.wait()

    # Clean up test database
    if os.path.exists("loiter_killer.db"):
        os.remove("loiter_killer.db")


class TestLoiterKillerService:
    """Test the Loiter Killer service."""

    @pytest.mark.asyncio
    async def test_service_starts_and_responds_to_health_check(
        self, loiter_killer_service
    ):
        """Test that the service starts and responds to health checks."""
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:9876/health")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}

    @pytest.mark.asyncio
    async def test_acquire_creates_new_vector_store_for_new_session(
        self, loiter_killer_service
    ):
        """Test that acquire creates a new vector store for a new session."""
        async with httpx.AsyncClient() as client:
            session_id = "test_session_123"

            # Make request
            response = await client.post(
                f"http://localhost:9876/session/{session_id}/acquire"
            )

            # Verify response
            assert response.status_code == 200
            data = response.json()
            assert "vector_store_id" in data
            assert data["vector_store_id"].startswith("vs_test_")
            assert data["reused"] is False
            assert data["files"] == []  # Deprecated field
            assert data["file_paths"] == []

    @pytest.mark.asyncio
    async def test_acquire_returns_existing_store_for_known_session(
        self, loiter_killer_service
    ):
        """Test that acquire returns existing vector store for known session."""
        async with httpx.AsyncClient() as client:
            session_id = "test_session_456"

            # First request - create new
            response1 = await client.post(
                f"http://localhost:9876/session/{session_id}/acquire"
            )
            assert response1.status_code == 200
            data1 = response1.json()
            vector_store_id = data1["vector_store_id"]
            assert data1["reused"] is False

            # Second request - should reuse
            response2 = await client.post(
                f"http://localhost:9876/session/{session_id}/acquire"
            )
            assert response2.status_code == 200
            data2 = response2.json()
            assert data2["vector_store_id"] == vector_store_id
            assert data2["reused"] is True
            assert data2["files"] == []  # Deprecated field
            assert data2["file_paths"] == []

    @pytest.mark.asyncio
    async def test_file_tracking(self, loiter_killer_service):
        """Test that files can be tracked for a session."""
        async with httpx.AsyncClient() as client:
            session_id = "test_session_789"

            # First acquire a session
            response1 = await client.post(
                f"http://localhost:9876/session/{session_id}/acquire"
            )
            assert response1.status_code == 200

            # Track some files
            file_paths = [
                "/path/to/file1.txt",
                "/path/to/file2.py",
                "/path/to/file3.md",
            ]
            response2 = await client.post(
                f"http://localhost:9876/session/{session_id}/files",
                json={"file_paths": file_paths},
            )
            assert response2.status_code == 200
            assert response2.json()["tracked"] == 3

            # Acquire again - should return the tracked files
            response3 = await client.post(
                f"http://localhost:9876/session/{session_id}/acquire"
            )
            assert response3.status_code == 200
            data3 = response3.json()
            assert data3["reused"] is True
            assert set(data3["file_paths"]) == set(file_paths)

    @pytest.mark.asyncio
    async def test_lease_renewal(self, loiter_killer_service):
        """Test that lease can be renewed."""
        async with httpx.AsyncClient() as client:
            session_id = "test_session_renewal"

            # First acquire a session
            response1 = await client.post(
                f"http://localhost:9876/session/{session_id}/acquire"
            )
            assert response1.status_code == 200

            # Renew the lease
            response2 = await client.post(
                f"http://localhost:9876/session/{session_id}/renew"
            )
            assert response2.status_code == 200
            assert response2.json()["status"] == "renewed"

            # Try to renew non-existent session
            response3 = await client.post(
                "http://localhost:9876/session/non_existent/renew"
            )
            assert response3.status_code == 404

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, loiter_killer_service):
        """Test that expired sessions are cleaned up."""
        import sqlite3

        async with httpx.AsyncClient() as client:
            session_id = "test_session_cleanup"

            # Acquire a session
            response1 = await client.post(
                f"http://localhost:9876/session/{session_id}/acquire"
            )
            assert response1.status_code == 200
            # vector_store_id = response1.json()["vector_store_id"]  # Not used

            # Track some files
            file_paths = ["/cleanup/file1.txt", "/cleanup/file2.txt"]
            response2 = await client.post(
                f"http://localhost:9876/session/{session_id}/files",
                json={"file_paths": file_paths},
            )
            assert response2.status_code == 200

            # Manually expire the session by updating database
            conn = sqlite3.connect("loiter_killer.db")
            expired_time = int(time.time()) - 7200  # 2 hours ago
            conn.execute(
                "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
                (expired_time, session_id),
            )
            conn.commit()
            conn.close()

            # Trigger cleanup (in real service this would be background task)
            response3 = await client.post("http://localhost:9876/cleanup")
            assert response3.status_code == 200

            # Verify session is gone
            response4 = await client.post(
                f"http://localhost:9876/session/{session_id}/renew"
            )
            assert response4.status_code == 404

    @pytest.mark.asyncio
    async def test_error_handling(self, loiter_killer_service):
        """Test error handling for various edge cases."""
        async with httpx.AsyncClient() as client:
            # Test tracking files for non-existent session
            response1 = await client.post(
                "http://localhost:9876/session/non_existent/files", json=["file_001"]
            )
            assert response1.status_code == 404

            # Test renewing non-existent session (already tested above)
            response2 = await client.post(
                "http://localhost:9876/session/non_existent/renew"
            )
            assert response2.status_code == 404

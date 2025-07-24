"""Test thread pool singleton safety."""

import pytest
import asyncio
import threading
from unittest.mock import patch, MagicMock
import mcp_the_force.utils.thread_pool as tp
from mcp_the_force.utils.thread_pool import get_shared_executor


class TestThreadPoolSingleton:
    """Test thread pool singleton implementation."""

    def setup_method(self):
        """Clear any existing instance before each test."""
        tp._shared_executor = None

    @pytest.mark.asyncio
    async def test_thread_pool_singleton_safety(self):
        """Test thread pool is created only once under concurrent access."""
        # Clear any existing instance
        tp._shared_executor = None

        executors = []

        async def get_executor():
            # Simulate concurrent access
            await asyncio.sleep(0.001)
            executors.append(get_shared_executor())

        # Run 100 concurrent attempts
        await asyncio.gather(*[get_executor() for _ in range(100)])

        # All should be the same instance
        assert len(set(id(e) for e in executors)) == 1
        assert all(e is executors[0] for e in executors)

    def test_thread_names(self):
        """Test that thread names use the configured prefix."""
        executor = get_shared_executor()

        # Submit a simple task
        future = executor.submit(lambda: threading.current_thread().name)
        thread_name = future.result()

        assert thread_name.startswith("force-worker")

    def test_thread_pool_uses_config(self):
        """Test that thread pool uses configured worker count."""
        # Clear any existing instance
        tp._shared_executor = None

        # Mock the settings at the module level where it's imported
        with patch("mcp_the_force.utils.thread_pool.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.mcp.thread_pool_workers = 5
            mock_get_settings.return_value = mock_settings

            executor = get_shared_executor()
            assert executor._max_workers == 5

    @pytest.mark.asyncio
    async def test_run_in_thread_pool(self):
        """Test run_in_thread_pool utility function."""
        from mcp_the_force.utils.thread_pool import run_in_thread_pool

        def blocking_function(x, y):
            """Simulate a blocking operation."""
            import time

            time.sleep(0.1)
            return x + y

        result = await run_in_thread_pool(blocking_function, 2, 3)
        assert result == 5

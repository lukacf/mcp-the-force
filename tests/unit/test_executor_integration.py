"""Test ToolExecutor integration with stable list feature."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from mcp_second_brain.tools.executor import ToolExecutor
from mcp_second_brain.tools.registry import ToolMetadata


class TestExecutorIntegration:
    """Test integration of stable list feature into ToolExecutor."""

    @pytest.mark.asyncio
    async def test_no_session_id_uses_fallback(self):
        """Test that without session_id, fallback prompt engine is used."""
        executor = ToolExecutor()

        # Create mock metadata
        metadata = ToolMetadata(
            id="test_tool",
            spec_class=MagicMock,
            model_config={
                "model_name": "test-model",
                "adapter_class": "openai",
                "timeout": 30,
            },
            parameters={},
        )

        # Mock dependencies
        with patch("mcp_second_brain.tools.executor.get_settings") as mock_settings:
            # Stable list is always enabled - no feature flag needed
            mock_settings.return_value.mcp.context_percentage = 0.85

            with patch.object(executor.validator, "validate", return_value={}):
                with patch.object(
                    executor.router,
                    "route",
                    return_value={
                        "prompt": {
                            "instructions": "test",
                            "output_format": "json",
                            "context": [],
                        },
                        "adapter": {},
                        "vector_store": [],
                        "session": {},  # No session_id
                        "structured_output": {},
                        "vector_store_ids": [],
                    },
                ):
                    with patch.object(
                        executor.prompt_engine,
                        "build",
                        new_callable=AsyncMock,
                        return_value="<prompt>test</prompt>",
                    ) as mock_build:
                        with patch(
                            "mcp_second_brain.adapters.get_adapter",
                            return_value=(
                                MagicMock(generate=AsyncMock(return_value="response")),
                                None,
                            ),
                        ):
                            result = await executor.execute(
                                metadata, instructions="test"
                            )

                            # Verify fallback path was used (no session_id)
                            mock_build.assert_called_once()
                            assert result == "response"

    @pytest.mark.asyncio
    async def test_stable_list_with_session_id(self):
        """Test that with session_id, stable list path is used."""
        executor = ToolExecutor()

        # Create mock metadata
        metadata = ToolMetadata(
            id="test_tool",
            spec_class=MagicMock,
            model_config={
                "model_name": "test-model",
                "adapter_class": "openai",
                "timeout": 30,
            },
            parameters={},
        )

        # Mock dependencies
        with patch("mcp_second_brain.tools.executor.get_settings") as mock_settings:
            # Stable list is always enabled - no feature flag needed
            mock_settings.return_value.mcp.context_percentage = 0.85

            with patch.object(executor.validator, "validate", return_value={}):
                with patch.object(
                    executor.router,
                    "route",
                    return_value={
                        "prompt": {
                            "instructions": "test",
                            "output_format": "json",
                            "context": ["/test"],
                        },
                        "adapter": {},
                        "vector_store": [],
                        "session": {"session_id": "test-session"},
                        "structured_output": {},
                        "vector_store_ids": [],
                    },
                ):
                    with patch(
                        "mcp_second_brain.tools.executor.StableListCache"
                    ) as mock_cache_class:
                        mock_cache = MagicMock()
                        mock_cache_class.return_value = mock_cache

                        with patch(
                            "mcp_second_brain.tools.executor.get_model_context_window",
                            return_value=100000,
                        ):
                            with patch(
                                "mcp_second_brain.tools.executor.build_context_with_stable_list",
                                new_callable=AsyncMock,
                                return_value=(
                                    [("/test/file.py", "content", 100)],
                                    [],
                                    "/test\n└── file.py",
                                ),
                            ) as mock_build:
                                with patch.object(
                                    executor.prompt_engine,
                                    "build",
                                    new_callable=AsyncMock,
                                ) as mock_old_build:
                                    with patch(
                                        "mcp_second_brain.adapters.get_adapter",
                                        return_value=(
                                            MagicMock(
                                                generate=AsyncMock(
                                                    return_value="response"
                                                )
                                            ),
                                            None,
                                        ),
                                    ):
                                        result = await executor.execute(
                                            metadata,
                                            instructions="test",
                                            context=["/test"],
                                        )

                                        # Verify new path was used
                                        mock_build.assert_called_once()
                                        mock_old_build.assert_not_called()
                                        assert result == "response"

    @pytest.mark.asyncio
    async def test_no_session_id_uses_fallback_even_with_context(self):
        """Test that without session_id, fallback is used even with context files."""
        executor = ToolExecutor()

        # Create mock metadata
        metadata = ToolMetadata(
            id="test_tool",
            spec_class=MagicMock,
            model_config={
                "model_name": "test-model",
                "adapter_class": "openai",
                "timeout": 30,
            },
            parameters={},
        )

        # Mock dependencies
        with patch("mcp_second_brain.tools.executor.get_settings") as mock_settings:
            # Stable list is always enabled - no feature flag needed
            mock_settings.return_value.mcp.context_percentage = 0.85

            with patch.object(executor.validator, "validate", return_value={}):
                with patch.object(
                    executor.router,
                    "route",
                    return_value={
                        "prompt": {
                            "instructions": "test",
                            "output_format": "json",
                            "context": [],
                        },
                        "adapter": {},
                        "vector_store": [],
                        "session": {},  # No session_id
                        "structured_output": {},
                        "vector_store_ids": [],
                    },
                ):
                    with patch.object(
                        executor.prompt_engine,
                        "build",
                        new_callable=AsyncMock,
                        return_value="<prompt>test</prompt>",
                    ) as mock_build:
                        with patch(
                            "mcp_second_brain.adapters.get_adapter",
                            return_value=(
                                MagicMock(generate=AsyncMock(return_value="response")),
                                None,
                            ),
                        ):
                            result = await executor.execute(
                                metadata, instructions="test"
                            )

                            # Verify old path was used
                            mock_build.assert_called_once()
                            assert result == "response"

    @pytest.mark.asyncio
    async def test_vector_store_created_with_overflow_files(self):
        """Test that vector store is created with overflow files in new path."""
        executor = ToolExecutor()

        # Create mock metadata
        metadata = ToolMetadata(
            id="test_tool",
            spec_class=MagicMock,
            model_config={
                "model_name": "test-model",
                "adapter_class": "openai",
                "timeout": 30,
            },
            parameters={},
        )

        # Mock dependencies
        with patch("mcp_second_brain.tools.executor.get_settings") as mock_settings:
            # Stable list is always enabled - no feature flag needed
            mock_settings.return_value.mcp.context_percentage = 0.85

            with patch.object(executor.validator, "validate", return_value={}):
                with patch.object(
                    executor.router,
                    "route",
                    return_value={
                        "prompt": {
                            "instructions": "test",
                            "output_format": "json",
                            "context": ["/test"],
                        },
                        "adapter": {},
                        "vector_store": [],
                        "session": {"session_id": "test-session"},
                        "structured_output": {},
                        "vector_store_ids": [],
                    },
                ):
                    with patch("mcp_second_brain.tools.executor.StableListCache"):
                        with patch(
                            "mcp_second_brain.tools.executor.get_model_context_window",
                            return_value=100000,
                        ):
                            # Return inline files and overflow files
                            with patch(
                                "mcp_second_brain.tools.executor.build_context_with_stable_list",
                                new_callable=AsyncMock,
                                return_value=(
                                    [("/test/inline.py", "content", 100)],
                                    ["/test/overflow1.py", "/test/overflow2.py"],
                                    "/test\n├── inline.py\n├── overflow1.py attached\n└── overflow2.py attached",
                                ),
                            ):
                                with patch.object(
                                    executor.vector_store_manager,
                                    "create",
                                    new_callable=AsyncMock,
                                    return_value="vs-123",
                                ) as mock_create_vs:
                                    with patch(
                                        "mcp_second_brain.adapters.get_adapter",
                                        return_value=(
                                            MagicMock(
                                                generate=AsyncMock(
                                                    return_value="response"
                                                )
                                            ),
                                            None,
                                        ),
                                    ):
                                        result = await executor.execute(
                                            metadata,
                                            instructions="test",
                                            context=["/test"],
                                        )

                                        # Verify vector store was created with overflow files
                                        mock_create_vs.assert_called_once_with(
                                            [
                                                "/test/overflow1.py",
                                                "/test/overflow2.py",
                                            ],
                                            session_id="test-session",
                                        )
                                        assert result == "response"

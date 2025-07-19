"""
Integration tests for vector store functionality.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock
from mcp_second_brain.tools.vector_store_manager import VectorStoreManager
from mcp_second_brain.tools.executor import executor
from mcp_second_brain.tools.registry import get_tool

# Import definitions to ensure tools are registered
import mcp_second_brain.tools.definitions  # noqa: F401


class TestVectorStoreIntegration:
    """Test vector store creation and usage."""

    @pytest.mark.asyncio
    async def test_vector_store_creation(self, tmp_path, mock_env, mock_openai_factory):
        """Test creating a vector store from files."""
        # Create test files
        (tmp_path / "doc1.py").write_text("def function1(): pass")
        (tmp_path / "doc2.py").write_text("def function2(): pass")
        (tmp_path / "doc3.md").write_text("# Documentation\nThis is a test.")

        # Mock vector store creation
        mock_openai_factory.vector_stores.create.return_value = Mock(
            id="vs_test123", status="completed"
        )
        mock_openai_factory.vector_stores.file_batches.upload_and_poll.return_value = (
            Mock(status="completed", file_counts=Mock(completed=3, failed=0, total=3))
        )

        # Create vector store
        vs_manager = VectorStoreManager()
        # Gather files from the directory
        from mcp_second_brain.utils.fs import gather_file_paths

        files = gather_file_paths([str(tmp_path)])
        vs_id = await vs_manager.create(files)

        assert vs_id == "vs_test123"

        # Verify vector store was created
        mock_openai_factory.vector_stores.create.assert_called_once()

        # Verify files were uploaded
        mock_openai_factory.vector_stores.file_batches.upload_and_poll.assert_called_once()

    @pytest.mark.asyncio
    async def test_vector_store_file_filtering(
        self, tmp_path, mock_env, mock_openai_factory
    ):
        """Test that vector store respects file filtering rules."""
        # Create various file types
        (tmp_path / "code.py").write_text("# Python code")
        (tmp_path / "data.json").write_text('{"key": "value"}')
        (tmp_path / "binary.exe").write_bytes(b"\x00\x01\x02")
        (tmp_path / ".gitignore").write_text("*.log")
        (tmp_path / "debug.log").write_text("Debug info")

        # Mock vector store
        uploaded_files = []

        def mock_upload(files, **kwargs):
            uploaded_files.extend(files)
            return Mock(
                status="completed",
                file_counts=Mock(completed=len(files), failed=0, total=len(files)),
            )

        mock_openai_factory.vector_stores.create.return_value = Mock(id="vs_filter")
        mock_openai_factory.vector_stores.file_batches.upload_and_poll.side_effect = (
            mock_upload
        )

        # Process attachments
        vs_manager = VectorStoreManager()
        from mcp_second_brain.utils.fs import gather_file_paths

        files = gather_file_paths([str(tmp_path)])
        await vs_manager.create(files)

        # Check uploaded files
        uploaded_names = [
            Path(f.name).name for f in uploaded_files if hasattr(f, "name")
        ]

        # Should include text files
        assert any("code.py" in name for name in uploaded_names)
        assert any("data.json" in name for name in uploaded_names)

        # Should not include binary or ignored files
        assert not any("binary.exe" in name for name in uploaded_names)
        assert not any("debug.log" in name for name in uploaded_names)

    @pytest.mark.asyncio
    async def test_empty_vector_store(self, tmp_path, mock_openai_factory):
        """Test handling of empty directories for vector store."""
        # Empty directory
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        # Should handle gracefully
        tool_metadata = get_tool("chat_with_gpt4_1")
        if not tool_metadata:
            raise ValueError("Tool chat_with_gpt4_1 not found")
        result = await executor.execute(
            tool_metadata,
            instructions="Analyze",
            output_format="text",
            context=[str(empty_dir)],
            session_id="test-empty",
        )

        # Parse MockAdapter response
        import json

        data = json.loads(result)
        assert data["mock"] is True

        # Vector store might not be created for empty input
        # or created with no files - both are acceptable
        # The key thing is the tool execution completes successfully

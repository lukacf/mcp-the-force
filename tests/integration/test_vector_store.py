"""
Integration tests for vector store functionality.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from mcp_second_brain.tools.vector_store_manager import VectorStoreManager
from mcp_second_brain.tools.integration import execute_tool_direct


class TestVectorStoreIntegration:
    """Test vector store creation and usage."""
    
    @pytest.mark.asyncio
    async def test_vector_store_creation(self, tmp_path, mock_openai_client):
        """Test creating a vector store from files."""
        # Create test files
        (tmp_path / "doc1.py").write_text("def function1(): pass")
        (tmp_path / "doc2.py").write_text("def function2(): pass")
        (tmp_path / "doc3.md").write_text("# Documentation\nThis is a test.")
        
        # Mock vector store creation
        mock_openai_client.beta.vector_stores.create.return_value = Mock(
            id="vs_test123",
            status="completed"
        )
        mock_openai_client.beta.vector_stores.file_batches.upload_and_poll.return_value = Mock(
            status="completed",
            file_counts=Mock(completed=3, failed=0)
        )
        
        # Create vector store
        vs_manager = VectorStoreManager()
        vs_id = await vs_manager.process_attachments([str(tmp_path)])
        
        assert vs_id == "vs_test123"
        
        # Verify vector store was created
        mock_openai_client.beta.vector_stores.create.assert_called_once()
        
        # Verify files were uploaded
        mock_openai_client.beta.vector_stores.file_batches.upload_and_poll.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_vector_store_with_attachments(self, temp_project, mock_openai_client):
        """Test using attachments parameter to trigger vector store."""
        # Create additional files for attachments
        docs_dir = temp_project / "docs"
        docs_dir.mkdir()
        (docs_dir / "api.md").write_text("# API Documentation\n\nAPI details here.")
        (docs_dir / "guide.md").write_text("# User Guide\n\nHow to use the system.")
        
        # Mock vector store operations
        mock_openai_client.beta.vector_stores.create.return_value = Mock(id="vs_attach")
        mock_openai_client.beta.vector_stores.file_batches.upload_and_poll.return_value = Mock(
            status="completed"
        )
        
        # Mock response
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock(
            message=AsyncMock(
                parsed=AsyncMock(response="Analysis using vector store"),
                refusal=None
            )
        )]
        mock_openai_client.beta.chat.completions.parse.return_value = mock_response
        
        # Execute tool with attachments
        result = await execute_tool_direct(
            "chat_with_gpt4_1",
            instructions="Analyze the documentation",
            output_format="summary",
            context=[str(temp_project / "src")],  # Small context
            attachments=[str(docs_dir)],  # Large attachments
            session_id="test-vs"
        )
        
        assert "Analysis using vector store" in result
        
        # Verify vector store was created
        mock_openai_client.beta.vector_stores.create.assert_called()
        
        # Verify the model call included vector store ID
        call_kwargs = mock_openai_client.beta.chat.completions.parse.call_args[1]
        assert "tools" in call_kwargs or "tool_resources" in call_kwargs
    
    @pytest.mark.asyncio
    async def test_vector_store_file_filtering(self, tmp_path, mock_openai_client):
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
            return Mock(status="completed", file_counts=Mock(completed=len(files)))
        
        mock_openai_client.beta.vector_stores.create.return_value = Mock(id="vs_filter")
        mock_openai_client.beta.vector_stores.file_batches.upload_and_poll.side_effect = mock_upload
        
        # Process attachments
        vs_manager = VectorStoreManager()
        await vs_manager.process_attachments([str(tmp_path)])
        
        # Check uploaded files
        uploaded_names = [Path(f.name).name for f in uploaded_files if hasattr(f, 'name')]
        
        # Should include text files
        assert any("code.py" in name for name in uploaded_names)
        assert any("data.json" in name for name in uploaded_names)
        
        # Should not include binary or ignored files
        assert not any("binary.exe" in name for name in uploaded_names)
        assert not any("debug.log" in name for name in uploaded_names)
    
    @pytest.mark.asyncio
    async def test_empty_vector_store(self, tmp_path, mock_openai_client):
        """Test handling of empty directories for vector store."""
        # Empty directory
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        
        # Mock response
        mock_openai_client.beta.chat.completions.parse.return_value = Mock(
            choices=[Mock(message=Mock(parsed=Mock(response="No files"), refusal=None))]
        )
        
        # Should handle gracefully
        result = await execute_tool_direct(
            "chat_with_gpt4_1",
            instructions="Analyze",
            output_format="text",
            context=[],
            attachments=[str(empty_dir)],
            session_id="test-empty"
        )
        
        assert result == "No files"
        
        # Vector store might not be created for empty input
        # or created with no files - both are acceptable
    
    @pytest.mark.asyncio
    async def test_vector_store_error_handling(self, tmp_path, mock_openai_client):
        """Test handling of vector store creation failures."""
        (tmp_path / "file.txt").write_text("content")
        
        # Simulate vector store creation failure
        mock_openai_client.beta.vector_stores.create.side_effect = Exception("VS creation failed")
        
        # Should raise appropriate error
        with pytest.raises(Exception, match="creation failed|vector store"):
            await execute_tool_direct(
                "chat_with_gpt4_1",
                instructions="Test",
                output_format="text",
                context=[],
                attachments=[str(tmp_path)],
                session_id="test-fail"
            )
    
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_large_attachment_handling(self, tmp_path, mock_openai_client):
        """Test handling of large attachment sets."""
        # Create many files
        for i in range(100):
            (tmp_path / f"file{i}.txt").write_text(f"Content of file {i}\n" * 100)
        
        # Mock successful handling
        mock_openai_client.beta.vector_stores.create.return_value = Mock(id="vs_large")
        mock_openai_client.beta.vector_stores.file_batches.upload_and_poll.return_value = Mock(
            status="completed",
            file_counts=Mock(completed=100)
        )
        mock_openai_client.beta.chat.completions.parse.return_value = Mock(
            choices=[Mock(message=Mock(parsed=Mock(response="Processed large set"), refusal=None))]
        )
        
        # Should handle without timeout
        result = await execute_tool_direct(
            "chat_with_gpt4_1",
            instructions="Analyze all files",
            output_format="summary",
            context=[],
            attachments=[str(tmp_path)],
            session_id="test-large"
        )
        
        assert "Processed large set" in result
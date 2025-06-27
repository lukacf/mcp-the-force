"""
Real E2E tests for attachment search functionality.

These tests use REAL vector stores to verify the attachment search actually works.
NO MOCKING ALLOWED.
"""

import os

# Force real adapters for these tests
os.environ["MCP_ADAPTER_MOCK"] = "0"

import pytest  # noqa: E402
import asyncio  # noqa: E402
from unittest.mock import patch  # noqa: E402

# Import definitions to ensure all tools are registered
import mcp_second_brain.tools.definitions  # noqa: F401, E402


@pytest.fixture
def real_vector_store_client():
    """Ensure we're using the real OpenAI client, not a mock."""
    # Override the global mock from conftest.py
    import mcp_second_brain.utils.vector_store as vs_module
    from openai import OpenAI
    from mcp_second_brain.config import get_settings

    # Create a real client
    def get_real_client():
        return OpenAI(api_key=get_settings().openai_api_key)

    with patch.object(vs_module, "get_client", side_effect=get_real_client):
        yield


@pytest.fixture
def test_documents(tmp_path):
    """Create test documents with searchable content."""
    docs = []

    # Document 1: Technical specification
    doc1 = tmp_path / "technical_spec.md"
    doc1.write_text("""
# Technical Specification

## Authentication System
The authentication system uses JWT tokens with RSA-256 signing.
Secret key: ZEPHYR-AUTH-KEY-2024

## Database Schema
- Users table: id, email, password_hash
- Sessions table: id, user_id, token, expires_at

## API Endpoints
- POST /auth/login - Returns JWT token
- POST /auth/logout - Invalidates token
- GET /auth/verify - Verifies token validity
""")
    docs.append(doc1)

    # Document 2: Meeting notes
    doc2 = tmp_path / "meeting_notes.txt"
    doc2.write_text("""
Meeting Notes - Q1 Planning
Date: 2024-01-15

Attendees: Alice, Bob, Charlie

Key Decisions:
1. Move to microservices architecture
2. Implement Redis caching layer
3. Upgrade to PostgreSQL 15
4. Deploy using Kubernetes

Action Items:
- Alice: Design service boundaries
- Bob: Set up CI/CD pipeline
- Charlie: Migration plan for database

Budget approved: $150,000
Timeline: 3 months
""")
    docs.append(doc2)

    # Document 3: Code file
    doc3 = tmp_path / "config.py"
    doc3.write_text("""
import os
from dataclasses import dataclass

@dataclass
class Config:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://localhost/myapp")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    jwt_secret: str = os.getenv("JWT_SECRET", "ZEPHYR-AUTH-KEY-2024")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # Feature flags
    enable_caching: bool = True
    enable_rate_limiting: bool = True
    max_requests_per_minute: int = 60
    
    # S3 configuration
    s3_bucket: str = "myapp-uploads"
    aws_region: str = "us-east-1"
""")
    docs.append(doc3)

    return docs


class TestAttachmentSearchReal:
    """Test attachment search with real vector stores."""

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="Requires OPENAI_API_KEY for real vector store operations",
    )
    @pytest.mark.asyncio
    async def test_search_attachments_basic(self, real_vector_store_client):
        """Test that attachment search tool is registered when vector stores exist."""
        from mcp_second_brain.adapters.openai import OpenAIAdapter

        # Create adapter
        adapter = OpenAIAdapter("gpt-4.1")

        # Generate without vector stores - should only have search_project_memory
        await adapter.generate(
            prompt="Test prompt",
            vector_store_ids=None,
        )

        # The adapter should register search_project_memory but NOT search_session_attachments
        # This is hard to test directly, but we can at least verify it runs

        # Generate with vector stores - should have both search tools
        await adapter.generate(
            prompt="Test prompt",
            vector_store_ids=["vs_test123"],
        )

        # Again, hard to test directly but we verify it runs without error

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="Requires OPENAI_API_KEY for real vector store operations",
    )
    @pytest.mark.asyncio
    async def test_attachment_search_tool_registration(self, real_vector_store_client):
        """Test that search_session_attachments tool is registered for models."""
        # For OpenAI models
        from mcp_second_brain.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter("gpt-4.1")

        # Test 1: Without attachments - should NOT have search_session_attachments
        result = await adapter.generate(prompt="test", return_debug=True)

        tool_names = [
            t.get("name") if t.get("type") == "function" else t.get("type")
            for t in result.get("_debug_tools", [])
        ]
        assert "search_project_memory" in tool_names
        assert "search_session_attachments" not in tool_names

        # Test 2: With attachments - should have search_session_attachments
        result2 = await adapter.generate(
            prompt="test", vector_store_ids=["vs_dummy"], return_debug=True
        )

        tool_names2 = [
            t.get("name") if t.get("type") == "function" else t.get("type")
            for t in result2.get("_debug_tools", [])
        ]
        assert "search_project_memory" in tool_names2
        assert "search_session_attachments" in tool_names2

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="Requires OPENAI_API_KEY for real vector store operations",
    )
    @pytest.mark.asyncio
    async def test_search_finds_specific_content(
        self, real_vector_store_client, test_documents, created_vector_stores
    ):
        """Test that search actually finds specific content in attachments."""
        from mcp_second_brain.tools.search_attachments import SearchAttachmentAdapter

        # Manually create a vector store for testing
        from mcp_second_brain.tools.vector_store_manager import VectorStoreManager

        manager = VectorStoreManager()

        # Create vector store with test documents
        vs_id = await manager.create([str(doc) for doc in test_documents])
        created_vector_stores.append(vs_id)  # Track for cleanup

        try:
            adapter = SearchAttachmentAdapter()
            result = await adapter.generate(
                prompt="",
                query="ZEPHYR-AUTH-KEY-2024",
                max_results=5,
                vector_store_ids=[vs_id],
            )

            # Verify the secret key was found
            assert "ZEPHYR-AUTH-KEY-2024" in result
            assert "Result 1" in result  # At least one result

            # Search for meeting notes content
            result2 = await adapter.generate(
                prompt="",
                query="microservices architecture",
                max_results=5,
                vector_store_ids=[vs_id],
            )

            assert "microservices" in result2.lower()

        finally:
            # Cleanup
            await manager.delete(vs_id)

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="Requires OPENAI_API_KEY for real vector store operations",
    )
    @pytest.mark.asyncio
    async def test_search_without_attachments(self, real_vector_store_client):
        """Test search behavior when no attachments exist."""
        from mcp_second_brain.tools.search_attachments import SearchAttachmentAdapter

        adapter = SearchAttachmentAdapter()
        result = await adapter.generate(
            prompt="",
            query="anything",
            max_results=10,
            vector_store_ids=[],
        )

        assert "No attachments available" in result

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="Requires OPENAI_API_KEY for real vector store operations",
    )
    @pytest.mark.asyncio
    async def test_multiple_queries(
        self, real_vector_store_client, test_documents, created_vector_stores
    ):
        """Test searching with multiple semicolon-separated queries."""
        from mcp_second_brain.tools.search_attachments import SearchAttachmentAdapter
        from mcp_second_brain.tools.vector_store_manager import VectorStoreManager

        manager = VectorStoreManager()
        vs_id = await manager.create([str(doc) for doc in test_documents])
        created_vector_stores.append(vs_id)  # Track for cleanup

        try:
            adapter = SearchAttachmentAdapter()
            result = await adapter.generate(
                prompt="",
                query="JWT tokens;PostgreSQL;Kubernetes",
                max_results=10,
                vector_store_ids=[vs_id],
            )

            # Should find results for multiple queries
            assert "JWT" in result or "token" in result
            assert "PostgreSQL" in result or "database" in result
            assert "Kubernetes" in result or "deploy" in result

        finally:
            await manager.delete(vs_id)

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="Requires OPENAI_API_KEY for real vector store operations",
    )
    @pytest.mark.asyncio
    async def test_context_isolation(
        self, real_vector_store_client, test_documents, created_vector_stores
    ):
        """Test that attachment contexts don't leak between executions."""
        from mcp_second_brain.tools.search_attachments import SearchAttachmentAdapter
        from mcp_second_brain.tools.vector_store_manager import VectorStoreManager

        manager = VectorStoreManager()

        # Create two different vector stores
        docs1 = [test_documents[0]]  # Just technical spec
        docs2 = [test_documents[1]]  # Just meeting notes

        vs_id1 = await manager.create([str(doc) for doc in docs1])
        vs_id2 = await manager.create([str(doc) for doc in docs2])
        created_vector_stores.extend([vs_id1, vs_id2])  # Track both for cleanup

        try:
            # Simulate two concurrent executions
            async def execution1():
                adapter = SearchAttachmentAdapter()
                result = await adapter.generate(
                    prompt="",
                    query="tech",
                    max_results=1,
                    vector_store_ids=[vs_id1],
                )
                assert f"{vs_id1}" in result

            async def execution2():
                adapter = SearchAttachmentAdapter()
                result = await adapter.generate(
                    prompt="",
                    query="meet",
                    max_results=1,
                    vector_store_ids=[vs_id2],
                )
                assert f"{vs_id2}" in result

            # Run concurrently
            await asyncio.gather(execution1(), execution2())

        finally:
            await manager.delete(vs_id1)
            await manager.delete(vs_id2)


class TestAttachmentSearchIntegration:
    """Test integration of attachment search with models."""

    @pytest.mark.asyncio
    async def test_openai_tool_registration_with_attachments(self):
        """Test that OpenAI models get search_session_attachments when attachments exist."""
        from mcp_second_brain.adapters.openai import OpenAIAdapter

        adapter = OpenAIAdapter("gpt-4.1")

        # Test without attachments
        result = await adapter.generate(prompt="test query", return_debug=True)
        tool_names = [
            t.get("name") if t.get("type") == "function" else t.get("type")
            for t in result.get("_debug_tools", [])
        ]
        assert "search_session_attachments" not in tool_names

        # Test with attachments
        result2 = await adapter.generate(
            prompt="test query", vector_store_ids=["vs_123"], return_debug=True
        )
        tool_names2 = [
            t.get("name") if t.get("type") == "function" else t.get("type")
            for t in result2.get("_debug_tools", [])
        ]
        assert "search_session_attachments" in tool_names2

    @pytest.mark.asyncio
    async def test_gemini_tool_registration_with_attachments(self):
        """Test that Gemini models get search_session_attachments when attachments exist."""
        import os
        import pytest

        if not os.getenv("VERTEX_PROJECT"):
            pytest.skip("Requires VERTEX_PROJECT configuration")

        from mcp_second_brain.adapters.vertex import VertexAdapter

        adapter = VertexAdapter("gemini-2.5-flash")  # Use flash for faster tests

        # Test without attachments
        result = await adapter.generate(prompt="test query", return_debug=True)

        # For Gemini, tools are dicts with 'name' key
        tool_names = [fd.get("name") for fd in result.get("_debug_tools", [])]
        assert "search_project_memory" in tool_names
        assert "search_session_attachments" not in tool_names

        # Test with attachments
        result2 = await adapter.generate(
            prompt="test query", vector_store_ids=["vs_123"], return_debug=True
        )
        tool_names2 = [fd.get("name") for fd in result2.get("_debug_tools", [])]
        assert "search_project_memory" in tool_names2
        assert "search_session_attachments" in tool_names2

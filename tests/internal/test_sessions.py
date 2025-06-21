"""
Integration tests for multi-turn session management.
"""
import pytest
import asyncio
from unittest.mock import Mock
from mcp_second_brain.tools.executor import executor
from mcp_second_brain.tools.registry import get_tool
# Import definitions to ensure tools are registered
import mcp_second_brain.tools.definitions  # noqa: F401
from mcp_second_brain.session_cache import session_cache


class TestSessionManagement:
    """Test multi-turn conversation session management."""
    
    @pytest.fixture(autouse=True)
    def clear_session_cache(self):
        """Clear session cache before each test."""
        cache = session_cache
        cache._data.clear()
        yield
        cache._data.clear()
    
    @pytest.mark.asyncio
    async def test_basic_session_continuity(self, mock_openai_client):
        """Test basic session continuity across multiple calls."""
        # First response
        response1 = Mock(
            id="resp_001",
            output_text="Hello! I can help with that."
        )
        
        # Second response
        response2 = Mock(
            id="resp_002",
            output_text="Continuing from before, here's the answer."
        )
        
        # Set up mock to return different responses
        mock_openai_client.responses.create.side_effect = [response1, response2]
        
        # First call
        tool_metadata = get_tool("chat_with_o3")
        if not tool_metadata:
            raise ValueError("Tool chat_with_o3 not found")
        result1 = await executor.execute(
            tool_metadata,
            instructions="I need help with Python decorators",
            output_format="explanation",
            context=[],
            session_id="decorator-help"
        )
        
        assert "Hello! I can help" in result1
        
        # Second call with same session
        result2 = await executor.execute(
            tool_metadata,
            instructions="Can you show me a concrete example?",
            output_format="code",
            context=[],
            session_id="decorator-help"
        )
        
        assert "Continuing from before" in result2
        
        # Verify second call included previous response ID
        second_call = mock_openai_client.responses.create.call_args_list[1]
        _, kwargs = second_call
        assert kwargs.get("previous_response_id") == "resp_001"
    
    @pytest.mark.asyncio
    async def test_multiple_sessions_isolated(self, mock_openai_client):
        """Test that different sessions are isolated from each other."""
        responses = [
            Mock(id=f"resp_{i}", output_text=f"Response for session {i//2 + 1}")
            for i in range(4)
        ]
        
        mock_openai_client.responses.create.side_effect = responses
        
        # Two parallel conversations
        tool_metadata = get_tool("chat_with_o3")
        if not tool_metadata:
            raise ValueError("Tool chat_with_o3 not found")
        results = await asyncio.gather(
            executor.execute(
                tool_metadata,
                instructions="First message session 1",
                output_format="text",
                context=[],
                session_id="session-1"
            ),
            executor.execute(
                tool_metadata,
                instructions="First message session 2",
                output_format="text",
                context=[],
                session_id="session-2"
            ),
            executor.execute(
                tool_metadata,
                instructions="Second message session 1",
                output_format="text",
                context=[],
                session_id="session-1"
            ),
            executor.execute(
                tool_metadata,
                instructions="Second message session 2",
                output_format="text",
                context=[],
                session_id="session-2"
            )
        )
        
        # Check responses are for correct sessions
        # Since we're running in parallel, order might vary
        # Just verify we got 2 responses for each session
        session1_responses = [r for r in results if "session 1" in r]
        session2_responses = [r for r in results if "session 2" in r]
        
        assert len(session1_responses) == 2
        assert len(session2_responses) == 2
    
    @pytest.mark.asyncio
    async def test_session_with_different_models(self, mock_openai_client):
        """Test using same session ID across different OpenAI models."""
        responses = [
            Mock(id="resp_o3", output_text="Response from o3"),
            Mock(id="resp_gpt4", output_text="Response from gpt4 continuing conversation")
        ]
        
        mock_openai_client.responses.create.side_effect = responses
        
        # Start with o3
        o3_metadata = get_tool("chat_with_o3")
        if not o3_metadata:
            raise ValueError("Tool chat_with_o3 not found")
        result1 = await executor.execute(
            o3_metadata,
            instructions="Start conversation",
            output_format="text",
            context=[],
            session_id="cross-model"
        )
        
        assert "Response from o3" in result1
        
        # Continue with gpt4
        gpt4_metadata = get_tool("chat_with_gpt4_1")
        if not gpt4_metadata:
            raise ValueError("Tool chat_with_gpt4_1 not found")
        result2 = await executor.execute(
            gpt4_metadata,
            instructions="Continue conversation",
            output_format="text",
            context=[],
            session_id="cross-model"
        )
        
        assert "Response from gpt4" in result2
        
        # Should have used previous response ID
        second_call = mock_openai_client.responses.create.call_args_list[1]
        _, kwargs = second_call
        assert kwargs.get("previous_response_id") == "resp_o3"
    
    @pytest.mark.asyncio
    async def test_session_expiration(self, mock_openai_client):
        """Test that sessions expire after TTL."""
        from mcp_second_brain.session_cache import SessionCache
        from unittest.mock import patch
        
        # Create cache with very short TTL for testing
        cache = SessionCache(ttl=0.1)  # 100ms TTL
        
        with patch('mcp_second_brain.session_cache.session_cache', cache):
            response = Mock(id="resp_expire", output_text="Initial response")
            mock_openai_client.responses.create.return_value = response
            
            # First call
            tool_metadata = get_tool("chat_with_o3")
            if not tool_metadata:
                raise ValueError("Tool chat_with_o3 not found")
            await executor.execute(
                tool_metadata,
                instructions="Start",
                output_format="text",
                context=[],
                session_id="expire-test"
            )
            
            # Wait for expiration
            await asyncio.sleep(0.2)
            
            # Second call - should not have previous_response_id
            await executor.execute(
                tool_metadata,
                instructions="Continue",
                output_format="text",
                context=[],
                session_id="expire-test"
            )
            
            # Check second call didn't include expired session
            second_call = mock_openai_client.responses.create.call_args_list[1]
            _, kwargs = second_call
            assert kwargs.get("previous_response_id") is None
    
    @pytest.mark.asyncio
    async def test_gemini_ignores_session(self, mock_env, mock_vertex_client):
        """Test that Gemini models ignore session_id parameter."""
        mock_vertex_client.generate_content.return_value.text = "Gemini response"
        
        # Should work even with session_id (just ignored)
        tool_metadata = get_tool("chat_with_gemini25_flash")
        if not tool_metadata:
            raise ValueError("Tool chat_with_gemini25_flash not found")
        result = await executor.execute(
            tool_metadata,
            instructions="Test",
            output_format="text",
            context=[],
            session_id="ignored-session"  # This should be ignored
        )
        
        assert "Gemini response" in result
        
        # Verify generate_content was called without session info
        call_args = mock_vertex_client.generate_content.call_args
        # Should not have any session-related parameters
        assert "session" not in str(call_args).lower()
        assert "previous" not in str(call_args).lower()
    
    @pytest.mark.asyncio
    async def test_concurrent_session_updates(self, mock_openai_client):
        """Test that concurrent requests to same session handle properly."""
        # Mock responses with delays
        async def delayed_response(delay, resp_id, content):
            await asyncio.sleep(delay)
            return Mock(
                id=resp_id,
                output_text=content
            )
        
        # Set up mock to return responses with different delays
        mock_openai_client.responses.create.side_effect = [
            await delayed_response(0.1, "resp_1", "First response"),
            await delayed_response(0.05, "resp_2", "Second response"),
            await delayed_response(0.02, "resp_3", "Third response")
        ]
        
        # Launch three requests concurrently to same session
        tool_metadata = get_tool("chat_with_o3")
        if not tool_metadata:
            raise ValueError("Tool chat_with_o3 not found")
        tasks = [
            executor.execute(
                tool_metadata,
                instructions=f"Message {i}",
                output_format="text",
                context=[],
                session_id="concurrent-test"
            )
            for i in range(3)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should complete successfully
        assert len(results) == 3
        assert all("response" in r.lower() for r in results)
    
    @pytest.mark.asyncio
    async def test_session_with_context_changes(self, temp_project, mock_openai_client):
        """Test session continuity when context files change between calls."""
        # Initial response
        response1 = Mock(id="resp_ctx1", output_text="Analyzed initial files")
        
        # Response after context change
        response2 = Mock(id="resp_ctx2", output_text="Noticed new file added")
        
        mock_openai_client.responses.create.side_effect = [response1, response2]
        
        # First call with initial context
        tool_metadata = get_tool("chat_with_o3")
        if not tool_metadata:
            raise ValueError("Tool chat_with_o3 not found")
        await executor.execute(
            tool_metadata,
            instructions="Analyze this project",
            output_format="summary",
            context=[str(temp_project)],
            session_id="evolving-context"
        )
        
        # Add a new file
        (temp_project / "new_feature.py").write_text("def new_feature(): pass")
        
        # Second call with updated context
        result2 = await executor.execute(
            tool_metadata,
            instructions="What changed?",
            output_format="diff",
            context=[str(temp_project)],
            session_id="evolving-context"
        )
        
        assert "new file added" in result2
        
        # Should still maintain session continuity
        second_call = mock_openai_client.responses.create.call_args_list[1]
        _, kwargs = second_call
        assert kwargs.get("previous_response_id") == "resp_ctx1"
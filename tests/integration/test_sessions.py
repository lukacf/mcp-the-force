"""
Integration tests for multi-turn session management.
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from mcp_second_brain.tools.integration import execute_tool_direct
from mcp_second_brain.session_cache import get_session_cache


class TestSessionManagement:
    """Test multi-turn conversation session management."""
    
    @pytest.fixture(autouse=True)
    def clear_session_cache(self):
        """Clear session cache before each test."""
        cache = get_session_cache()
        cache._cache.clear()
        yield
        cache._cache.clear()
    
    @pytest.mark.asyncio
    async def test_basic_session_continuity(self, mock_openai_client):
        """Test basic session continuity across multiple calls."""
        # First response
        response1 = Mock(
            id="resp_001",
            choices=[Mock(message=Mock(
                parsed=Mock(response="Hello! I can help with that."),
                refusal=None
            ))]
        )
        
        # Second response
        response2 = Mock(
            id="resp_002",
            choices=[Mock(message=Mock(
                parsed=Mock(response="Continuing from before, here's the answer."),
                refusal=None
            ))]
        )
        
        # Set up mock to return different responses
        mock_openai_client.beta.chat.completions.parse.side_effect = [response1, response2]
        
        # First call
        result1 = await execute_tool_direct(
            "chat_with_o3",
            instructions="I need help with Python decorators",
            output_format="explanation",
            context=[],
            session_id="decorator-help"
        )
        
        assert "Hello! I can help" in result1
        
        # Second call with same session
        result2 = await execute_tool_direct(
            "chat_with_o3",
            instructions="Can you show me a concrete example?",
            output_format="code",
            context=[],
            session_id="decorator-help"
        )
        
        assert "Continuing from before" in result2
        
        # Verify second call included previous response ID
        second_call = mock_openai_client.beta.chat.completions.parse.call_args_list[1]
        metadata = second_call[1].get("metadata", {})
        assert metadata.get("previous_response_id") == "resp_001"
    
    @pytest.mark.asyncio
    async def test_multiple_sessions_isolated(self, mock_openai_client):
        """Test that different sessions are isolated from each other."""
        responses = [
            Mock(id=f"resp_{i}", choices=[Mock(message=Mock(
                parsed=Mock(response=f"Response for session {i//2 + 1}"),
                refusal=None
            ))]) for i in range(4)
        ]
        
        mock_openai_client.beta.chat.completions.parse.side_effect = responses
        
        # Two parallel conversations
        results = await asyncio.gather(
            execute_tool_direct(
                "chat_with_o3",
                instructions="First message session 1",
                output_format="text",
                context=[],
                session_id="session-1"
            ),
            execute_tool_direct(
                "chat_with_o3",
                instructions="First message session 2",
                output_format="text",
                context=[],
                session_id="session-2"
            ),
            execute_tool_direct(
                "chat_with_o3",
                instructions="Second message session 1",
                output_format="text",
                context=[],
                session_id="session-1"
            ),
            execute_tool_direct(
                "chat_with_o3",
                instructions="Second message session 2",
                output_format="text",
                context=[],
                session_id="session-2"
            )
        )
        
        # Check responses are for correct sessions
        assert "session 1" in results[0]
        assert "session 2" in results[1]
        assert "session 1" in results[2]
        assert "session 2" in results[3]
    
    @pytest.mark.asyncio
    async def test_session_with_different_models(self, mock_openai_client):
        """Test using same session ID across different OpenAI models."""
        responses = [
            Mock(id="resp_o3", choices=[Mock(message=Mock(
                parsed=Mock(response="Response from o3"),
                refusal=None
            ))]),
            Mock(id="resp_gpt4", choices=[Mock(message=Mock(
                parsed=Mock(response="Response from gpt4 continuing conversation"),
                refusal=None
            ))])
        ]
        
        mock_openai_client.beta.chat.completions.parse.side_effect = responses
        
        # Start with o3
        result1 = await execute_tool_direct(
            "chat_with_o3",
            instructions="Start conversation",
            output_format="text",
            context=[],
            session_id="cross-model"
        )
        
        assert "Response from o3" in result1
        
        # Continue with gpt4
        result2 = await execute_tool_direct(
            "chat_with_gpt4_1",
            instructions="Continue conversation",
            output_format="text",
            context=[],
            session_id="cross-model"
        )
        
        assert "Response from gpt4" in result2
        
        # Should have used previous response ID
        second_call = mock_openai_client.beta.chat.completions.parse.call_args_list[1]
        metadata = second_call[1].get("metadata", {})
        assert metadata.get("previous_response_id") == "resp_o3"
    
    @pytest.mark.asyncio
    async def test_session_expiration(self, mock_openai_client):
        """Test that sessions expire after TTL."""
        from mcp_second_brain.session_cache import SessionCache
        
        # Create cache with very short TTL for testing
        cache = SessionCache(ttl_seconds=0.1)  # 100ms TTL
        
        with patch('mcp_second_brain.session_cache.get_session_cache', return_value=cache):
            response = Mock(
                id="resp_expire",
                choices=[Mock(message=Mock(
                    parsed=Mock(response="Initial response"),
                    refusal=None
                ))]
            )
            mock_openai_client.beta.chat.completions.parse.return_value = response
            
            # First call
            await execute_tool_direct(
                "chat_with_o3",
                instructions="Start",
                output_format="text",
                context=[],
                session_id="expire-test"
            )
            
            # Wait for expiration
            await asyncio.sleep(0.2)
            
            # Second call - should not have previous_response_id
            await execute_tool_direct(
                "chat_with_o3",
                instructions="Continue",
                output_format="text",
                context=[],
                session_id="expire-test"
            )
            
            # Check second call didn't include expired session
            second_call = mock_openai_client.beta.chat.completions.parse.call_args_list[1]
            metadata = second_call[1].get("metadata", {})
            assert metadata.get("previous_response_id") is None
    
    @pytest.mark.asyncio
    async def test_gemini_ignores_session(self, mock_vertex_client):
        """Test that Gemini models ignore session_id parameter."""
        mock_vertex_client.generate_content.return_value.text = "Gemini response"
        
        # Should work even with session_id (just ignored)
        result = await execute_tool_direct(
            "chat_with_gemini25_flash",
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
                choices=[Mock(message=Mock(
                    parsed=Mock(response=content),
                    refusal=None
                ))]
            )
        
        # Set up mock to return responses with different delays
        mock_openai_client.beta.chat.completions.parse.side_effect = [
            await delayed_response(0.1, "resp_1", "First response"),
            await delayed_response(0.05, "resp_2", "Second response"),
            await delayed_response(0.02, "resp_3", "Third response")
        ]
        
        # Launch three requests concurrently to same session
        tasks = [
            execute_tool_direct(
                "chat_with_o3",
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
        response1 = Mock(
            id="resp_ctx1",
            choices=[Mock(message=Mock(
                parsed=Mock(response="Analyzed initial files"),
                refusal=None
            ))]
        )
        
        # Response after context change
        response2 = Mock(
            id="resp_ctx2",
            choices=[Mock(message=Mock(
                parsed=Mock(response="Noticed new file added"),
                refusal=None
            ))]
        )
        
        mock_openai_client.beta.chat.completions.parse.side_effect = [response1, response2]
        
        # First call with initial context
        result1 = await execute_tool_direct(
            "chat_with_o3",
            instructions="Analyze this project",
            output_format="summary",
            context=[str(temp_project)],
            session_id="evolving-context"
        )
        
        # Add a new file
        (temp_project / "new_feature.py").write_text("def new_feature(): pass")
        
        # Second call with updated context
        result2 = await execute_tool_direct(
            "chat_with_o3",
            instructions="What changed?",
            output_format="diff",
            context=[str(temp_project)],
            session_id="evolving-context"
        )
        
        assert "new file added" in result2
        
        # Should still maintain session continuity
        second_call = mock_openai_client.beta.chat.completions.parse.call_args_list[1]
        metadata = second_call[1].get("metadata", {})
        assert metadata.get("previous_response_id") == "resp_ctx1"
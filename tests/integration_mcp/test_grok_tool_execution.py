"""Integration tests for Grok adapter tool execution and session management."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_second_brain.adapters.grok.adapter import GrokAdapter
from mcp_second_brain.grok_session_cache import grok_session_cache


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for Grok adapter testing."""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    return client


@pytest.fixture
def grok_adapter_with_mock(mock_openai_client, monkeypatch):
    """Create Grok adapter with mocked OpenAI client."""
    # Set environment variable for the test
    monkeypatch.setenv("XAI_API_KEY", "test-api-key")

    with patch("mcp_second_brain.adapters.grok.adapter.AsyncOpenAI") as mock_openai:
        mock_openai.return_value = mock_openai_client

        adapter = GrokAdapter(model_name="grok-4")
        adapter.client = mock_openai_client
        return adapter


class TestGrokToolExecution:
    """Test Grok adapter tool execution functionality."""

    @pytest.mark.asyncio
    async def test_simple_conversation_without_tools(
        self, grok_adapter_with_mock, mock_openai_client
    ):
        """Test basic conversation without tool calls."""
        # Mock response without tool calls
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "Hello! How can I help you today?"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": "Hello! How can I help you today?",
        }
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 8
        mock_response.usage.total_tokens = 18

        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Test simple conversation
        result = await grok_adapter_with_mock.generate(prompt="Hello, can you help me?")

        assert result == "Hello! How can I help you today?"
        mock_openai_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_execution_search_project_memory(
        self, grok_adapter_with_mock, mock_openai_client
    ):
        """Test tool execution with search_project_memory."""
        # Mock first response with tool call
        mock_tool_call_response = MagicMock()
        mock_tool_call_response.choices = [MagicMock()]
        mock_tool_call_response.choices[0].message = MagicMock()
        mock_tool_call_response.choices[0].message.content = None
        mock_tool_call_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_123",
                function=MagicMock(
                    name="search_project_memory",
                    arguments='{"query": "Python programming", "max_results": 5}',
                ),
            )
        ]
        mock_tool_call_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "search_project_memory",
                        "arguments": '{"query": "Python programming", "max_results": 5}',
                    },
                }
            ],
        }

        # Mock final response after tool execution
        mock_final_response = MagicMock()
        mock_final_response.choices = [MagicMock()]
        mock_final_response.choices[0].message = MagicMock()
        mock_final_response.choices[
            0
        ].message.content = "Based on the search results, Python is a high-level programming language..."
        mock_final_response.choices[0].message.tool_calls = None
        mock_final_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": "Based on the search results, Python is a high-level programming language...",
        }

        # Set up mock to return different responses on subsequent calls
        mock_openai_client.chat.completions.create = AsyncMock(
            side_effect=[mock_tool_call_response, mock_final_response]
        )

        # Mock the search tool
        with patch(
            "mcp_second_brain.tools.search_memory.SearchMemoryAdapter"
        ) as mock_search_adapter:
            mock_adapter_instance = AsyncMock()
            mock_adapter_instance.generate = AsyncMock(
                return_value="Found 3 results about Python programming"
            )
            mock_search_adapter.return_value = mock_adapter_instance

            # Test tool execution
            result = await grok_adapter_with_mock.generate(
                prompt="Tell me about Python programming", vector_store_ids=None
            )

            assert (
                result
                == "Based on the search results, Python is a high-level programming language..."
            )

            # Verify tool was called
            mock_adapter_instance.generate.assert_called_once_with(
                prompt="Python programming", query="Python programming", max_results=5
            )

            # Verify OpenAI client was called twice (tool call + final response)
            assert mock_openai_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_tool_execution_search_session_attachments(
        self, grok_adapter_with_mock, mock_openai_client
    ):
        """Test tool execution with search_session_attachments."""
        # Mock tool call response
        mock_tool_call_response = MagicMock()
        mock_tool_call_response.choices = [MagicMock()]
        mock_tool_call_response.choices[0].message = MagicMock()
        mock_tool_call_response.choices[0].message.content = None
        mock_tool_call_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_456",
                function=MagicMock(
                    name="search_session_attachments",
                    arguments='{"query": "machine learning", "max_results": 10}',
                ),
            )
        ]
        mock_tool_call_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_456",
                    "type": "function",
                    "function": {
                        "name": "search_session_attachments",
                        "arguments": '{"query": "machine learning", "max_results": 10}',
                    },
                }
            ],
        }

        # Mock final response
        mock_final_response = MagicMock()
        mock_final_response.choices = [MagicMock()]
        mock_final_response.choices[0].message = MagicMock()
        mock_final_response.choices[
            0
        ].message.content = (
            "I found information about machine learning in the attachments..."
        )
        mock_final_response.choices[0].message.tool_calls = None
        mock_final_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": "I found information about machine learning in the attachments...",
        }

        mock_openai_client.chat.completions.create = AsyncMock(
            side_effect=[mock_tool_call_response, mock_final_response]
        )

        # Mock the attachment search tool
        with patch(
            "mcp_second_brain.tools.search_attachments.SearchAttachmentAdapter"
        ) as mock_search_adapter:
            mock_adapter_instance = AsyncMock()
            mock_adapter_instance.generate = AsyncMock(
                return_value="Found ML documentation in attachments"
            )
            mock_search_adapter.return_value = mock_adapter_instance

            # Test with vector store IDs
            result = await grok_adapter_with_mock.generate(
                prompt="Search for machine learning info",
                vector_store_ids=["vs-123", "vs-456"],
            )

            assert (
                result
                == "I found information about machine learning in the attachments..."
            )

            # Verify attachment search was called with vector store IDs
            mock_adapter_instance.generate.assert_called_once_with(
                prompt="machine learning",
                query="machine learning",
                max_results=10,
                vector_store_ids=["vs-123", "vs-456"],
            )

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_sequence(
        self, grok_adapter_with_mock, mock_openai_client
    ):
        """Test handling multiple tool calls in sequence."""
        # First tool call response
        mock_first_tool_response = MagicMock()
        mock_first_tool_response.choices = [MagicMock()]
        mock_first_tool_response.choices[0].message = MagicMock()
        mock_first_tool_response.choices[0].message.content = None
        mock_first_tool_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_1",
                function=MagicMock(
                    name="search_project_memory", arguments='{"query": "Python"}'
                ),
            )
        ]
        mock_first_tool_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "search_project_memory",
                        "arguments": '{"query": "Python"}',
                    },
                }
            ],
        }

        # Second tool call response
        mock_second_tool_response = MagicMock()
        mock_second_tool_response.choices = [MagicMock()]
        mock_second_tool_response.choices[0].message = MagicMock()
        mock_second_tool_response.choices[0].message.content = None
        mock_second_tool_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_2",
                function=MagicMock(
                    name="search_session_attachments", arguments='{"query": "examples"}'
                ),
            )
        ]
        mock_second_tool_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "search_session_attachments",
                        "arguments": '{"query": "examples"}',
                    },
                }
            ],
        }

        # Final response
        mock_final_response = MagicMock()
        mock_final_response.choices = [MagicMock()]
        mock_final_response.choices[0].message = MagicMock()
        mock_final_response.choices[
            0
        ].message.content = "Combined information from both searches..."
        mock_final_response.choices[0].message.tool_calls = None
        mock_final_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": "Combined information from both searches...",
        }

        mock_openai_client.chat.completions.create = AsyncMock(
            side_effect=[
                mock_first_tool_response,
                mock_second_tool_response,
                mock_final_response,
            ]
        )

        # Mock both search tools
        with patch(
            "mcp_second_brain.tools.search_memory.SearchMemoryAdapter"
        ) as mock_memory_adapter, patch(
            "mcp_second_brain.tools.search_attachments.SearchAttachmentAdapter"
        ) as mock_attachment_adapter:
            mock_memory_instance = AsyncMock()
            mock_memory_instance.generate = AsyncMock(
                return_value="Python info from memory"
            )
            mock_memory_adapter.return_value = mock_memory_instance

            mock_attachment_instance = AsyncMock()
            mock_attachment_instance.generate = AsyncMock(
                return_value="Python examples from attachments"
            )
            mock_attachment_adapter.return_value = mock_attachment_instance

            result = await grok_adapter_with_mock.generate(
                prompt="Find comprehensive Python information",
                vector_store_ids=["vs-789"],
            )

            assert result == "Combined information from both searches..."

            # Verify both tools were called
            mock_memory_instance.generate.assert_called_once()
            mock_attachment_instance.generate.assert_called_once()

            # Verify three API calls were made
            assert mock_openai_client.chat.completions.create.call_count == 3

    @pytest.mark.asyncio
    async def test_tool_execution_error_handling(
        self, grok_adapter_with_mock, mock_openai_client
    ):
        """Test error handling during tool execution."""
        # Mock tool call response
        mock_tool_call_response = MagicMock()
        mock_tool_call_response.choices = [MagicMock()]
        mock_tool_call_response.choices[0].message = MagicMock()
        mock_tool_call_response.choices[0].message.content = None
        mock_tool_call_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_error",
                function=MagicMock(
                    name="search_project_memory", arguments='{"query": "test"}'
                ),
            )
        ]
        mock_tool_call_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_error",
                    "type": "function",
                    "function": {
                        "name": "search_project_memory",
                        "arguments": '{"query": "test"}',
                    },
                }
            ],
        }

        # Final response after error
        mock_final_response = MagicMock()
        mock_final_response.choices = [MagicMock()]
        mock_final_response.choices[0].message = MagicMock()
        mock_final_response.choices[
            0
        ].message.content = "I encountered an error but will continue..."
        mock_final_response.choices[0].message.tool_calls = None
        mock_final_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": "I encountered an error but will continue...",
        }

        mock_openai_client.chat.completions.create = AsyncMock(
            side_effect=[mock_tool_call_response, mock_final_response]
        )

        # Mock tool to raise an exception
        with patch(
            "mcp_second_brain.tools.search_memory.SearchMemoryAdapter"
        ) as mock_search_adapter:
            mock_adapter_instance = AsyncMock()
            mock_adapter_instance.generate = AsyncMock(
                side_effect=Exception("Search failed")
            )
            mock_search_adapter.return_value = mock_adapter_instance

            result = await grok_adapter_with_mock.generate(
                prompt="Search for something that will fail"
            )

            assert result == "I encountered an error but will continue..."

            # Verify the error was handled gracefully
            mock_adapter_instance.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_tool_handling(
        self, grok_adapter_with_mock, mock_openai_client
    ):
        """Test handling of unknown/unsupported tools."""
        # Mock tool call with unknown tool
        mock_tool_call_response = MagicMock()
        mock_tool_call_response.choices = [MagicMock()]
        mock_tool_call_response.choices[0].message = MagicMock()
        mock_tool_call_response.choices[0].message.content = None
        mock_tool_call_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_unknown",
                function=MagicMock(name="unknown_tool", arguments='{"param": "value"}'),
            )
        ]
        mock_tool_call_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_unknown",
                    "type": "function",
                    "function": {
                        "name": "unknown_tool",
                        "arguments": '{"param": "value"}',
                    },
                }
            ],
        }

        # Final response after unknown tool
        mock_final_response = MagicMock()
        mock_final_response.choices = [MagicMock()]
        mock_final_response.choices[0].message = MagicMock()
        mock_final_response.choices[
            0
        ].message.content = "I tried to use an unknown tool..."
        mock_final_response.choices[0].message.tool_calls = None
        mock_final_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": "I tried to use an unknown tool...",
        }

        mock_openai_client.chat.completions.create = AsyncMock(
            side_effect=[mock_tool_call_response, mock_final_response]
        )

        result = await grok_adapter_with_mock.generate(
            prompt="Try to use an unknown tool"
        )

        assert result == "I tried to use an unknown tool..."

        # Verify two API calls were made
        assert mock_openai_client.chat.completions.create.call_count == 2


class TestGrokSessionManagement:
    """Test Grok session management and conversation continuity."""

    @pytest.mark.asyncio
    async def test_session_storage_and_retrieval(
        self, grok_adapter_with_mock, mock_openai_client
    ):
        """Test that sessions are properly stored and retrieved."""
        session_id = "test-session-storage"

        # Mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "Hello! I remember our conversation."
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": "Hello! I remember our conversation.",
        }

        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # First call to establish session
        await grok_adapter_with_mock.generate(prompt="Hello", session_id=session_id)

        # Second call to continue session
        await grok_adapter_with_mock.generate(
            prompt="Do you remember me?", session_id=session_id
        )

        # Verify session was passed to subsequent calls
        assert mock_openai_client.chat.completions.create.call_count == 2

        # Check that the second call included conversation history
        second_call_args = mock_openai_client.chat.completions.create.call_args_list[1]
        messages = second_call_args[1]["messages"]

        # Should have: user1, assistant1, user2
        assert len(messages) >= 3
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"
        assert messages[2]["content"] == "Do you remember me?"

    @pytest.mark.asyncio
    async def test_session_with_tool_calls_preservation(
        self, grok_adapter_with_mock, mock_openai_client
    ):
        """Test that tool calls are preserved in session history."""
        session_id = "test-session-tools"

        # Mock tool call response
        mock_tool_call_response = MagicMock()
        mock_tool_call_response.choices = [MagicMock()]
        mock_tool_call_response.choices[0].message = MagicMock()
        mock_tool_call_response.choices[0].message.content = None
        mock_tool_call_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_session",
                function=MagicMock(
                    name="search_project_memory", arguments='{"query": "test"}'
                ),
            )
        ]
        mock_tool_call_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_session",
                    "type": "function",
                    "function": {
                        "name": "search_project_memory",
                        "arguments": '{"query": "test"}',
                    },
                }
            ],
        }

        # Mock final response
        mock_final_response = MagicMock()
        mock_final_response.choices = [MagicMock()]
        mock_final_response.choices[0].message = MagicMock()
        mock_final_response.choices[0].message.content = "I found some information."
        mock_final_response.choices[0].message.tool_calls = None
        mock_final_response.choices[0].message.model_dump.return_value = {
            "role": "assistant",
            "content": "I found some information.",
        }

        mock_openai_client.chat.completions.create = AsyncMock(
            side_effect=[mock_tool_call_response, mock_final_response]
        )

        # Mock search tool
        with patch(
            "mcp_second_brain.tools.search_memory.SearchMemoryAdapter"
        ) as mock_search_adapter:
            mock_adapter_instance = AsyncMock()
            mock_adapter_instance.generate = AsyncMock(return_value="Search results")
            mock_search_adapter.return_value = mock_adapter_instance

            # First interaction with tool call
            result1 = await grok_adapter_with_mock.generate(
                prompt="Search for test information", session_id=session_id
            )

            assert result1 == "I found some information."

            # Continue session - should have tool call history
            mock_continue_response = MagicMock()
            mock_continue_response.choices = [MagicMock()]
            mock_continue_response.choices[0].message = MagicMock()
            mock_continue_response.choices[
                0
            ].message.content = "Based on the previous search..."
            mock_continue_response.choices[0].message.tool_calls = None
            mock_continue_response.choices[0].message.model_dump.return_value = {
                "role": "assistant",
                "content": "Based on the previous search...",
            }

            mock_openai_client.chat.completions.create = AsyncMock(
                return_value=mock_continue_response
            )

            result2 = await grok_adapter_with_mock.generate(
                prompt="What did you find earlier?", session_id=session_id
            )

            assert result2 == "Based on the previous search..."

            # Verify that the continued session included the complete history
            continue_call_args = mock_openai_client.chat.completions.create.call_args
            messages = continue_call_args[1]["messages"]

            # Should include: user1, assistant1 (tool call), tool result, assistant2 (final), user2
            assert len(messages) >= 5

            # Check that tool calls are preserved
            tool_call_found = any(msg.get("tool_calls") is not None for msg in messages)
            tool_result_found = any(msg.get("role") == "tool" for msg in messages)

            assert tool_call_found
            assert tool_result_found

    @pytest.mark.asyncio
    async def test_session_cleanup_on_adapter_methods(self):
        """Test that session cache methods work correctly."""
        session_id = "test-cleanup-session"

        # Test getting empty history
        empty_history = await grok_session_cache.get_history(session_id)
        assert empty_history == []

        # Test setting and getting history
        test_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        await grok_session_cache.set_history(session_id, test_history)
        retrieved_history = await grok_session_cache.get_history(session_id)

        assert retrieved_history == test_history

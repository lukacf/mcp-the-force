"""Integration test for describe_session that validates the full flow."""

import json
import time
import pytest
from mcp_the_force.local_services.describe_session import DescribeSessionService
from mcp_the_force.unified_session_cache import UnifiedSession, UnifiedSessionCache


@pytest.mark.asyncio
async def test_describe_session_passes_full_history_to_model(isolate_test_databases):
    """
    Ensures that describe_session correctly provides the full conversation history
    of the target session to the summarization model via the executor.
    """
    # 1. Arrange: Create a session with a known history
    original_session = UnifiedSession(
        project="mcp-the-force",
        tool="chat_with_o3",
        session_id="session-to-summarize",
        history=[
            {"role": "user", "content": "This is the conversation to be summarized."},
            {"role": "assistant", "content": "I understand. This is my response."},
            {"role": "user", "content": "Tell me more about the topic."},
            {
                "role": "assistant",
                "content": "Here are additional details about the topic.",
            },
        ],
        updated_at=int(time.time()),
    )
    await UnifiedSessionCache.set_session(original_session)

    # 2. Act: Call the service to generate a summary
    # The executor will use MockAdapter because of the test environment.
    service = DescribeSessionService()
    summary_result = await service.execute(
        session_id="session-to-summarize",
        summarization_model="chat_with_gemini25_flash",  # This tool uses MockAdapter in tests
    )

    # 3. Assert: Check the data received by the MockAdapter
    # The MockAdapter returns a JSON string detailing what it received.
    mock_adapter_input = json.loads(summary_result)

    # The 'prompt' field of the mock response contains the fully-formed prompt
    # passed to the model, which includes the conversation history.
    final_prompt = mock_adapter_input.get("prompt", "")

    # Verify that the original history is in the prompt sent to the summarizer
    assert "This is the conversation to be summarized." in final_prompt, (
        "History from the original session was missing from the summarizer's prompt."
    )

    assert "Tell me more about the topic." in final_prompt, (
        "Second user message was missing from the summarizer's prompt."
    )

    # Verify that the summarization instruction is also present
    assert "Summarize this conversation" in final_prompt, (
        "Summarization instruction was missing from the prompt."
    )

    # Verify the session_id in the mock response is the temp session
    assert mock_adapter_input["session_id"].startswith("temp-summary-"), (
        "The session_id should be a temporary session ID"
    )


@pytest.mark.asyncio
async def test_describe_session_cache_key_mismatch_bug(isolate_test_databases):
    """
    Specific test for the cache key mismatch bug where temp session was saved
    under original tool name but looked up under summarization tool name.
    """
    # Create an original session with chat_with_o3
    original_session = UnifiedSession(
        project="mcp-the-force",
        tool="chat_with_o3",
        session_id="test-key-mismatch",
        history=[{"role": "user", "content": "Test conversation for key mismatch"}],
        updated_at=int(time.time()),
    )
    await UnifiedSessionCache.set_session(original_session)

    service = DescribeSessionService()

    # Use a different tool for summarization
    result = await service.execute(
        session_id="test-key-mismatch", summarization_model="chat_with_gemini25_pro"
    )

    # Parse the mock response
    mock_response = json.loads(result)

    # The bug would cause this to fail because the executor couldn't find the temp session
    assert "Test conversation for key mismatch" in mock_response["prompt"], (
        "Cache key mismatch: temp session was not found by the executor"
    )

    # Also verify the model used was the one we requested
    assert mock_response["model"] == "gemini-2.5-pro", (
        "Wrong model was used for summarization"
    )

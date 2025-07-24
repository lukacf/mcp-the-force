"""Unit tests for OpenAI adapter tool executor."""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from mcp_the_force.adapters.openai.tool_exec import (
    ToolExecutor,
    BuiltInToolDispatcher,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_executor_handles_partial_failures():
    """Verify the executor returns both success and error results."""

    async def mock_dispatcher(name, args):
        if name == "success_tool":
            return {"status": "ok", "data": "test"}
        elif name == "fail_tool":
            raise ValueError("This tool failed")
        return "Unknown tool"

    executor = ToolExecutor(tool_dispatcher=mock_dispatcher)

    tool_calls = [
        {"call_id": "call_1", "name": "success_tool", "arguments": "{}"},
        {"call_id": "call_2", "name": "fail_tool", "arguments": "{}"},
    ]

    results = await executor.run_all(tool_calls)

    assert len(results) == 2

    # Check success result
    success_result = results[0]
    assert success_result["call_id"] == "call_1"
    assert success_result["type"] == "function_call_output"
    assert '"status": "ok"' in success_result["output"]

    # Check error result
    error_result = results[1]
    assert error_result["call_id"] == "call_2"
    assert error_result["type"] == "function_call_output"
    assert "failed: This tool failed" in error_result["output"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_executor_preserves_order():
    """Verify results are returned in the same order as input."""

    call_order = []

    async def mock_dispatcher(name, args):
        call_order.append(name)
        # Add delay to test concurrent execution
        await asyncio.sleep(0.01 if name == "fast" else 0.02)
        return f"Result for {name}"

    executor = ToolExecutor(tool_dispatcher=mock_dispatcher)

    tool_calls = [
        {"call_id": "1", "name": "slow", "arguments": "{}"},
        {"call_id": "2", "name": "fast", "arguments": "{}"},
        {"call_id": "3", "name": "medium", "arguments": "{}"},
    ]

    results = await executor.run_all(tool_calls)

    # Results should be in input order, not execution order
    assert results[0]["call_id"] == "1"
    assert results[1]["call_id"] == "2"
    assert results[2]["call_id"] == "3"

    # But execution can be in any order due to concurrency
    assert set(call_order) == {"slow", "fast", "medium"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_executor_handles_json_arguments():
    """Verify the executor correctly parses JSON arguments."""

    received_args = None

    async def mock_dispatcher(name, args):
        nonlocal received_args
        received_args = args
        return "ok"

    executor = ToolExecutor(tool_dispatcher=mock_dispatcher)

    tool_calls = [
        {
            "call_id": "test",
            "name": "test_tool",
            "arguments": json.dumps({"key": "value", "number": 42}),
        }
    ]

    await executor.run_all(tool_calls)

    assert received_args == {"key": "value", "number": 42}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_executor_handles_malformed_json():
    """Verify the executor handles malformed JSON gracefully."""

    received_args = None

    async def mock_dispatcher(name, args):
        nonlocal received_args
        received_args = args
        return "ok"

    executor = ToolExecutor(tool_dispatcher=mock_dispatcher)

    tool_calls = [
        {"call_id": "test", "name": "test_tool", "arguments": "not valid json"}
    ]

    results = await executor.run_all(tool_calls)

    # Should default to empty dict on parse error
    assert received_args == {}
    assert results[0]["output"] == "ok"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_executor_empty_list():
    """Verify the executor handles empty tool call list."""

    executor = ToolExecutor(tool_dispatcher=AsyncMock())
    results = await executor.run_all([])
    assert results == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_executor_handles_object_like_calls():
    """Verify the executor handles object-like tool calls (with attributes)."""

    received_name = None

    async def mock_dispatcher(name, args):
        nonlocal received_name
        received_name = name
        return "ok"

    executor = ToolExecutor(tool_dispatcher=mock_dispatcher)

    # Create a mock object with attributes instead of dict
    mock_call = MagicMock()
    mock_call.call_id = "obj_call_1"
    mock_call.name = "object_tool"
    mock_call.arguments = "{}"

    results = await executor.run_all([mock_call])

    assert received_name == "object_tool"
    assert results[0]["call_id"] == "obj_call_1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_builtin_tool_dispatcher_search_history():
    """Test the built-in tool dispatcher for search_project_history."""

    dispatcher = BuiltInToolDispatcher()

    with patch(
        "mcp_the_force.tools.search_history.SearchHistoryAdapter"
    ) as mock_adapter:
        mock_instance = AsyncMock()
        mock_instance.generate.return_value = {"results": ["memory1", "memory2"]}
        mock_adapter.return_value = mock_instance

        result = await dispatcher.dispatch(
            "search_project_history", {"query": "test query", "max_results": 10}
        )

        mock_instance.generate.assert_called_once_with(
            prompt="test query",
            query="test query",
            max_results=10,
            store_types=["conversation", "commit"],
        )
        assert result == {"results": ["memory1", "memory2"]}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_builtin_tool_dispatcher_unknown_tool():
    """Test the built-in tool dispatcher with unknown tool."""

    dispatcher = BuiltInToolDispatcher()

    with pytest.raises(ValueError, match="Unknown built-in tool: unknown_tool"):
        await dispatcher.dispatch("unknown_tool", {})

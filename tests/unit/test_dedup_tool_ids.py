"""Tests for _dedup_tool_ids function to ensure call/output pairs stay in sync."""

from mcp_the_force.adapters.litellm_base import _dedup_tool_ids


def test_dedup_keeps_call_output_pairs_in_sync():
    """Ensure function_call and function_call_output maintain matching call_ids."""
    conversation = [
        {"type": "function_call", "call_id": "call_123"},
        {"type": "function_call_output", "call_id": "call_123"},
    ]

    _dedup_tool_ids(conversation)

    # Both should keep the same call_id
    assert conversation[0]["call_id"] == "call_123"
    assert conversation[1]["call_id"] == "call_123"


def test_dedup_renames_duplicate_pairs_together():
    """When duplicate call_ids exist, paired messages should get the same new ID."""
    conversation = [
        {"type": "function_call", "call_id": "call_123"},
        {"type": "function_call_output", "call_id": "call_123"},
        {"type": "function_call", "call_id": "call_123"},  # duplicate
        {"type": "function_call_output", "call_id": "call_123"},  # duplicate
    ]

    _dedup_tool_ids(conversation)

    # First pair should keep original
    assert conversation[0]["call_id"] == "call_123"
    assert conversation[1]["call_id"] == "call_123"

    # Second pair should both get the same new ID
    assert conversation[2]["call_id"] == conversation[3]["call_id"]
    assert conversation[2]["call_id"] == "call_123-dup2"


def test_dedup_handles_tool_use_blocks():
    """Ensure tool_use blocks in content also maintain ID consistency."""
    conversation = [
        {
            "type": "message",
            "content": [{"type": "tool_use", "id": "tool_1"}],
        },
        {
            "type": "message",
            "content": [{"type": "tool_result", "id": "tool_1"}],
        },
    ]

    _dedup_tool_ids(conversation)

    # Both should keep the same ID
    assert conversation[0]["content"][0]["id"] == "tool_1"
    # Note: tool_result doesn't get deduplicated, only tool_use


def test_dedup_mixed_call_ids():
    """Test deduplication with mixed unique and duplicate call_ids."""
    conversation = [
        {"type": "function_call", "call_id": "call_A"},
        {"type": "function_call_output", "call_id": "call_A"},
        {"type": "function_call", "call_id": "call_B"},
        {"type": "function_call_output", "call_id": "call_B"},
        {"type": "function_call", "call_id": "call_A"},  # duplicate of first
        {"type": "function_call_output", "call_id": "call_A"},  # duplicate of second
    ]

    _dedup_tool_ids(conversation)

    # First pairs keep original IDs
    assert conversation[0]["call_id"] == "call_A"
    assert conversation[1]["call_id"] == "call_A"
    assert conversation[2]["call_id"] == "call_B"
    assert conversation[3]["call_id"] == "call_B"

    # Duplicate pair gets renamed together
    assert conversation[4]["call_id"] == conversation[5]["call_id"]
    assert conversation[4]["call_id"] == "call_A-dup2"


def test_dedup_none_call_ids():
    """Ensure None call_ids are handled gracefully."""
    conversation = [
        {"type": "function_call", "call_id": None},
        {"type": "function_call_output"},  # missing call_id
    ]

    _dedup_tool_ids(conversation)

    # Should not crash, None values unchanged
    assert conversation[0]["call_id"] is None
    assert "call_id" not in conversation[1]


def test_dedup_overlapping_calls():
    """Test overlapping calls - multiple calls with same ID before any outputs."""
    conversation = [
        {"type": "function_call", "call_id": "call_X"},  # First call
        {"type": "function_call", "call_id": "call_X"},  # Second call (overlapping!)
        {"type": "function_call_output", "call_id": "call_X"},  # Output for first
        {"type": "function_call_output", "call_id": "call_X"},  # Output for second
    ]

    _dedup_tool_ids(conversation)

    # First call keeps original ID
    assert conversation[0]["call_id"] == "call_X"

    # Second call gets renamed (duplicate detected even though first hasn't closed)
    assert conversation[1]["call_id"] == "call_X-dup2"

    # First output matches first call
    assert conversation[2]["call_id"] == "call_X"

    # Second output matches second call (FIFO ordering)
    assert conversation[3]["call_id"] == "call_X-dup2"


def test_dedup_three_overlapping_calls():
    """Test three overlapping calls with same ID."""
    conversation = [
        {"type": "function_call", "call_id": "call_Y"},
        {"type": "function_call", "call_id": "call_Y"},
        {"type": "function_call", "call_id": "call_Y"},
        {"type": "function_call_output", "call_id": "call_Y"},
        {"type": "function_call_output", "call_id": "call_Y"},
        {"type": "function_call_output", "call_id": "call_Y"},
    ]

    _dedup_tool_ids(conversation)

    # All calls get unique IDs
    assert conversation[0]["call_id"] == "call_Y"
    assert conversation[1]["call_id"] == "call_Y-dup2"
    assert conversation[2]["call_id"] == "call_Y-dup3"

    # Outputs match in FIFO order
    assert conversation[3]["call_id"] == "call_Y"
    assert conversation[4]["call_id"] == "call_Y-dup2"
    assert conversation[5]["call_id"] == "call_Y-dup3"

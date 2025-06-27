"""Helper functions for OpenAI adapter tests."""

import json
from unittest.mock import MagicMock, AsyncMock
from typing import List, Optional, Dict, Any


def setup_background_flow_mocks(
    mock_client: AsyncMock,
    retrieve_responses: List[MagicMock],
    create_ids: Optional[List[str]] = None,
) -> None:
    """Configure a mock client for background polling flow.

    Args:
        mock_client: The mocked OpenAI client
        retrieve_responses: List of responses that will be returned by retrieve()
        create_ids: Optional list of IDs for create() responses. If not provided,
                   IDs will be generated as resp_0, resp_1, etc.
    """
    # Generate IDs if not provided
    if create_ids is None:
        create_ids = [f"resp_{i}" for i in range(len(retrieve_responses))]

    # Create simple job objects for create() to return
    create_jobs = [MagicMock(id=job_id) for job_id in create_ids]

    # Ensure each retrieve response has the corresponding ID and completed status
    for i, response in enumerate(retrieve_responses):
        if not hasattr(response, "id"):
            response.id = create_ids[i]
        if not hasattr(response, "status"):
            response.status = "completed"

    # Set up the side effects
    mock_client.responses.create.side_effect = create_jobs
    mock_client.responses.retrieve.side_effect = retrieve_responses


def setup_streaming_flow_mocks(
    mock_client: AsyncMock, stream_responses: List[List[MagicMock]]
) -> None:
    """Configure a mock client for streaming flow.

    Args:
        mock_client: The mocked OpenAI client
        stream_responses: List of stream event lists (one per API call)
    """
    # Create async iterators for each stream
    streams = []
    for events in stream_responses:
        stream = AsyncMock()
        stream.__aiter__.return_value = events
        streams.append(stream)

    mock_client.responses.create.side_effect = streams


def create_function_call_response(
    response_id: str,
    call_id: str,
    function_name: str,
    arguments: Dict[str, Any],
    status: str = "completed",
) -> MagicMock:
    """Create a mock response with a function call."""
    # Create tool call as a dict to avoid MagicMock attribute issues
    tool_call = {
        "type": "function_call",
        "call_id": call_id,
        "name": function_name,
        "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
    }

    return MagicMock(
        id=response_id,
        status=status,
        output=[tool_call],  # List of dicts, not MagicMocks
    )


def create_text_response(
    response_id: str, text: str, status: str = "completed"
) -> MagicMock:
    """Create a mock response with text output."""
    return MagicMock(id=response_id, status=status, output_text=text)

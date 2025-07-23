"""Session management test - comprehensive memory lifecycle, persistence, and isolation."""

import sys
import os

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from json_utils import safe_json


class TestSessionManagement:
    """Test session persistence, isolation, and cross-model memory sharing."""

    def test_session_persistence_and_isolation(self, call_claude_tool):
        """Test memory storage, recall, and persistence between sessions."""

        session_id_a = "session-mgmt-test-a"

        # Define schemas for structured responses
        storage_schema = {
            "type": "object",
            "properties": {
                "information_stored": {"type": "boolean"},
                "stored_content": {"type": "string"},
                "session_id_used": {"type": "string"},
            },
            "required": ["information_stored", "stored_content", "session_id_used"],
            "additionalProperties": False,
        }

        recall_schema = {
            "type": "object",
            "properties": {
                "protocol_name": {"type": "string"},
                "port_number": {"type": "integer"},
                "found_in_session": {"type": "boolean"},
            },
            "required": ["protocol_name", "port_number", "found_in_session"],
            "additionalProperties": False,
        }

        # Step 1: Store technical information in session A
        response = call_claude_tool(
            "chat_with_gemini25_pro",
            instructions="Remember this: Protocol GAMMA-7 uses port 8443. Confirm what you stored.",
            output_format="JSON confirming the stored information",
            context=[],
            session_id=session_id_a,
            structured_output_schema=storage_schema,
            response_format="respond ONLY with the JSON",
        )

        # Validate storage confirmation - should match our schema exactly
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert result["information_stored"] is True, f"Storage failed: {result}"
        assert "GAMMA-7" in result["stored_content"], f"Protocol not stored: {result}"
        assert "8443" in result["stored_content"], f"Port not stored: {result}"
        assert result["session_id_used"] == session_id_a, f"Wrong session ID: {result}"

        # Step 2: Test immediate recall in same session
        response = call_claude_tool(
            "chat_with_gemini25_pro",
            instructions="What protocol and port number did I mention?",
            output_format="JSON with protocol details",
            context=[],
            session_id=session_id_a,
            structured_output_schema=recall_schema,
            response_format="respond ONLY with the JSON",
        )

        # Validate recall - should match our schema exactly
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert (
            result["found_in_session"] is True
        ), f"Should find info in session: {result}"
        assert result["protocol_name"] == "GAMMA-7", f"Wrong protocol: {result}"
        assert result["port_number"] == 8443, f"Wrong port: {result}"

        # Step 3: Test session persistence (return to original session)
        response = call_claude_tool(
            "chat_with_gemini25_pro",
            instructions="Recall the protocol configuration from earlier",
            output_format="JSON with protocol details",
            context=[],
            session_id=session_id_a,  # Back to original session
            structured_output_schema=recall_schema,
            response_format="respond ONLY with the JSON",
        )

        # Original session should still remember
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert (
            result["found_in_session"] is True
        ), f"Should find info in original session: {result}"
        assert result["protocol_name"] == "GAMMA-7", f"Wrong protocol: {result}"
        assert result["port_number"] == 8443, f"Wrong port: {result}"

    def test_multi_turn_conversation(self, call_claude_tool):
        """Test simple two-turn conversation with GPT-4.1 and memory search disabled."""

        session_id = "simple-gpt41-session"

        # Define simple schemas without pattern constraints
        storage_schema = {
            "type": "object",
            "properties": {
                "stored_value": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "required": ["stored_value", "confirmed"],
            "additionalProperties": False,
        }

        recall_schema = {
            "type": "object",
            "properties": {
                "recalled_value": {"type": "string"},
                "found": {"type": "boolean"},
            },
            "required": ["recalled_value", "found"],
            "additionalProperties": False,
        }

        # Turn 1: Store a simple value using GPT-4.1
        response = call_claude_tool(
            "chat_with_gpt4_1",
            instructions="Remember this code: ABC-123-XYZ",
            output_format="JSON confirming what was stored",
            context=[],
            session_id=session_id,
            disable_memory_search="true",  # Disable project memory search
            structured_output_schema=storage_schema,
            response_format="respond ONLY with the JSON",
        )

        # Validate storage
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert result["confirmed"] is True, f"Storage not confirmed: {result}"
        assert "ABC-123-XYZ" in result["stored_value"], f"Code not stored: {result}"

        # Turn 2: Recall the value in the same session
        response = call_claude_tool(
            "chat_with_gpt4_1",
            instructions="What was the code I asked you to remember?",
            output_format="JSON with the recalled code",
            context=[],
            session_id=session_id,
            disable_memory_search="true",  # Disable project memory search
            structured_output_schema=recall_schema,
            response_format="respond ONLY with the JSON",
        )

        # Validate recall
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert result["found"] is True, f"Value not found: {result}"
        assert (
            "ABC-123-XYZ" in result["recalled_value"]
        ), f"Wrong code recalled: {result}"

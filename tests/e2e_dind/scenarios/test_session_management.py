"""Session management test - comprehensive memory lifecycle, persistence, and isolation."""

import sys
import os
import random
import string

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from json_utils import safe_json


def generate_random_protocol():
    """Generate a random protocol name like ALPHA-X7K."""
    prefix = random.choice(["ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON"])
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"{prefix}-{suffix}"


def generate_random_port():
    """Generate a random port number between 1024 and 65535."""
    return random.randint(1024, 65535)


class TestSessionManagement:
    """Test session persistence, isolation, and cross-model memory sharing."""

    def test_session_persistence_and_isolation(self, call_claude_tool):
        """Test memory storage, recall, and persistence between sessions."""

        session_id_a = f"session-mgmt-test-{random.randint(1000, 9999)}"
        
        # Generate random test data
        protocol_name = generate_random_protocol()
        port_number = generate_random_port()

        # Define schemas for structured responses
        storage_schema = {
            "type": "object",
            "properties": {
                "information_stored": {"type": "boolean"},
                "stored_content": {"type": "string"},
            },
            "required": ["information_stored", "stored_content"],
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
            instructions=f"I need you to remember this information: Protocol {protocol_name} uses port {port_number}. Please acknowledge that you have stored this information.",
            output_format="JSON confirming the stored information",
            context=[],
            session_id=session_id_a,
            structured_output_schema=storage_schema,
            response_format="respond ONLY with the JSON",
            disable_memory_search="true",
        )

        # Validate storage confirmation - should match our schema exactly
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert result["information_stored"] is True, f"Storage failed: {result}"
        assert protocol_name in result["stored_content"], f"Protocol not stored: {result}"
        assert str(port_number) in result["stored_content"], f"Port not stored: {result}"

        # Step 2: Test immediate recall in same session
        response = call_claude_tool(
            "chat_with_gemini25_pro",
            instructions="What protocol and port number did I mention?",
            output_format="JSON with protocol details",
            context=[],
            session_id=session_id_a,
            structured_output_schema=recall_schema,
            response_format="respond ONLY with the JSON",
            disable_memory_search="true",
        )

        # Validate recall - should match our schema exactly
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert (
            result["found_in_session"] is True
        ), f"Should find info in session: {result}"
        # Accept both protocol name alone or with "Protocol" prefix
        assert protocol_name in result["protocol_name"], f"Wrong protocol: {result}"
        assert result["port_number"] == port_number, f"Wrong port: {result}"

        # Step 3: Test session persistence (return to original session)
        response = call_claude_tool(
            "chat_with_gemini25_pro",
            instructions="Recall the protocol configuration from earlier",
            output_format="JSON with protocol details",
            context=[],
            session_id=session_id_a,  # Back to original session
            structured_output_schema=recall_schema,
            response_format="respond ONLY with the JSON",
            disable_memory_search="true",
        )

        # Original session should still remember
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert (
            result["found_in_session"] is True
        ), f"Should find info in original session: {result}"
        # Accept both protocol name alone or with "Protocol" prefix
        assert protocol_name in result["protocol_name"], f"Wrong protocol: {result}"
        assert result["port_number"] == port_number, f"Wrong port: {result}"

    def test_multi_turn_conversation(self, call_claude_tool):
        """Test simple two-turn conversation with GPT-4.1 and memory search disabled."""

        session_id = f"simple-gpt41-session-{random.randint(1000, 9999)}"
        
        # Generate random code
        code_parts = [
            ''.join(random.choices(string.ascii_uppercase, k=3)),
            str(random.randint(100, 999)),
            ''.join(random.choices(string.ascii_uppercase, k=3))
        ]
        test_code = '-'.join(code_parts)

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
            "chat_with_gpt41",
            instructions=f"Remember this code: {test_code}",
            output_format="JSON confirming what was stored",
            context=[],
            session_id=session_id,
            disable_memory_search="true",  # Disable project history search
            structured_output_schema=storage_schema,
            response_format="respond ONLY with the JSON",
        )

        # Validate storage
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert result["confirmed"] is True, f"Storage not confirmed: {result}"
        assert test_code in result["stored_value"], f"Code not stored: {result}"

        # Turn 2: Recall the value in the same session
        response = call_claude_tool(
            "chat_with_gpt41",
            instructions="What was the code I asked you to remember?",
            output_format="JSON with the recalled code",
            context=[],
            session_id=session_id,
            disable_memory_search="true",  # Disable project history search
            structured_output_schema=recall_schema,
            response_format="respond ONLY with the JSON",
        )

        # Validate recall
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert result["found"] is True, f"Value not found: {result}"
        assert (
            test_code in result["recalled_value"]
        ), f"Wrong code recalled: {result}"

    def test_cross_model_history_search(self, call_claude_tool):
        """Test that one model can search project history to find another model's conversations."""

        session_id = f"cross-model-history-test-{random.randint(1000, 9999)}"
        
        # Generate unique test data that won't conflict with other tests
        protocol_name = generate_random_protocol()
        port_number = generate_random_port()

        # Define schema for search results
        search_schema = {
            "type": "object",
            "properties": {
                "found_protocol": {"type": "boolean"},
                "protocol_name": {"type": "string"},
                "port_number": {"type": "integer"},
                "results_count": {"type": "integer"},
            },
            "required": [
                "found_protocol",
                "protocol_name",
                "port_number",
                "results_count",
            ],
            "additionalProperties": False,
        }

        # Step 1: Store unique information with GPT-4.1
        response = call_claude_tool(
            "chat_with_gpt41",
            instructions=f"Remember this network configuration: Protocol {protocol_name} operates on port {port_number}",
            output_format="Acknowledge what you've stored",
            context=[],
            session_id=session_id,
            disable_memory_search="true",  # Ensure we're testing real session storage
        )

        # Simple validation that it was stored
        assert protocol_name in response, f"Protocol not mentioned in response: {response}"
        assert str(port_number) in response, f"Port not mentioned in response: {response}"

        # Give memory storage time to complete
        import time

        time.sleep(2)

        # Step 2: Use Gemini Flash to search project history for the information
        response = call_claude_tool(
            "chat_with_gemini25_flash",
            instructions=f"Use the search_project_history function to search for information about Protocol {protocol_name} and its port number",
            output_format="JSON with search results based on what you find",
            context=[],
            session_id=f"different-session-{random.randint(1000, 9999)}",  # Different session to ensure it's using history search
            structured_output_schema=search_schema,
            response_format="respond ONLY with the JSON",
        )

        # Validate that Gemini found the information through history search
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert (
            result["found_protocol"] is True
        ), f"Protocol not found in history: {result}"
        assert protocol_name in result["protocol_name"], f"Wrong protocol found: {result}"
        assert result["port_number"] == port_number, f"Wrong port found: {result}"
        assert result["results_count"] > 0, f"No search results returned: {result}"

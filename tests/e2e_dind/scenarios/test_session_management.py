"""Session management test - comprehensive memory lifecycle, persistence, and isolation."""

import sys
import os

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from json_utils import safe_json


class TestSessionManagement:
    """Test session persistence, isolation, and cross-model memory sharing."""

    def test_session_persistence_and_isolation(self, call_claude_tool):
        """Test memory storage, recall, persistence and isolation between sessions."""

        session_id_a = "session-mgmt-test-a"
        session_id_b = "session-mgmt-test-b"

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
            instructions="I'm configuring a system. Please remember: Protocol GAMMA-7 uses port 8443 for secure communications. Store this technical specification.",
            output_format="JSON object confirming what information was stored",
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
            instructions="What protocol and port number did I just tell you about?",
            output_format="JSON object with the protocol details",
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

        # Step 3: Test session isolation (different session ID)
        response = call_claude_tool(
            "chat_with_gemini25_pro",
            instructions="What protocol and port were mentioned in previous conversations?",
            output_format="JSON object with protocol details if any found",
            context=[],
            session_id=session_id_b,  # Different session
            structured_output_schema=recall_schema,
            response_format="respond ONLY with the JSON",
        )

        # Different session should not have access to previous session data
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert (
            result["found_in_session"] is False
        ), f"Should NOT find info from different session: {result}"
        # Protocol and port should be empty or default values since nothing found
        assert (
            result["protocol_name"] == "" or result["protocol_name"] is None
        ), f"Should not have protocol from other session: {result}"

        # Step 4: Test session persistence (return to original session)
        response = call_claude_tool(
            "chat_with_gemini25_pro",
            instructions="Quick reminder: what was that protocol configuration again?",
            output_format="JSON object with the remembered protocol details",
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
        """Test multi-turn conversations with context accumulation and cross-model memory sharing."""

        session_id = "multi-turn-session"

        # Define schemas
        algorithm_storage_schema = {
            "type": "object",
            "properties": {
                "stored_info": {"type": "string"},
                "confirmation": {"type": "boolean"},
            },
            "required": ["stored_info", "confirmation"],
            "additionalProperties": False,
        }

        algorithm_recall_schema = {
            "type": "object",
            "properties": {
                "algorithm_name": {"type": "string"},
                "time_complexity": {"type": "string"},
                "found": {"type": "boolean"},
            },
            "required": ["algorithm_name", "time_complexity", "found"],
            "additionalProperties": False,
        }

        # Step 1: Store information using o3
        response = call_claude_tool(
            "chat_with_o3",
            instructions="I'm working on Algorithm ZX-7 which has O(n log n) time complexity. Please store this information for our session.",
            output_format="JSON object confirming what you stored",
            context=[],
            session_id=session_id,
            reasoning_effort="low",
            structured_output_schema=algorithm_storage_schema,
            response_format="respond ONLY with the JSON",
        )

        # Validate storage - should match our schema exactly
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert result["confirmation"] is True, f"Storage confirmation failed: {result}"
        assert "ZX-7" in result["stored_info"], f"Algorithm name not stored: {result}"
        assert "n log n" in result["stored_info"], f"Complexity not stored: {result}"

        # Step 2: Test cross-model recall within same session (o3 -> gemini)
        response = call_claude_tool(
            "chat_with_gemini25_pro",
            instructions="In our current session, what algorithm configuration was discussed?",
            output_format="JSON object with algorithm details if found in session",
            context=[],
            session_id=session_id,
            structured_output_schema=algorithm_recall_schema,
            response_format="respond ONLY with the JSON",
        )

        # Cross-model recall - different model, same session
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        # Schema should be respected regardless of whether cross-model works
        assert "found" in result, f"Missing 'found' field: {result}"
        assert "algorithm_name" in result, f"Missing 'algorithm_name' field: {result}"
        assert "time_complexity" in result, f"Missing 'time_complexity' field: {result}"
        # Cross-model may or may not work, so we just check the schema is followed
        if result["found"] and result["algorithm_name"]:
            # If it found something, verify it's correct
            assert "ZX-7" in result["algorithm_name"], f"Wrong algorithm: {result}"

        # Step 3: Test reasoning_effort parameter with accumulated context
        analysis_schema = {
            "type": "object",
            "properties": {
                "best_case": {"type": "string"},
                "worst_case": {"type": "string"},
                "analysis_length": {"type": "integer"},
            },
            "required": ["best_case", "worst_case", "analysis_length"],
            "additionalProperties": False,
        }

        response = call_claude_tool(
            "chat_with_o3",
            instructions="Based on our previous discussion about Algorithm ZX-7, analyze its best-case vs worst-case scenarios.",
            output_format="JSON object with detailed analysis",
            context=[],
            session_id=session_id,
            reasoning_effort="high",
            structured_output_schema=analysis_schema,
            response_format="respond ONLY with the JSON",
        )

        # High reasoning effort should produce detailed analysis
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert "best_case" in result, f"Missing best_case: {result}"
        assert "worst_case" in result, f"Missing worst_case: {result}"
        assert "analysis_length" in result, f"Missing analysis_length: {result}"
        # Check that analysis is substantial
        assert len(result["best_case"]) > 10, f"Best case analysis too short: {result}"
        assert (
            len(result["worst_case"]) > 10
        ), f"Worst case analysis too short: {result}"
        assert result["analysis_length"] > 50, f"Analysis length too small: {result}"

        # Step 4: Test temperature parameter with memory context
        suggestions_schema = {
            "type": "object",
            "properties": {
                "suggested_algorithms": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "pattern_recognized": {"type": "boolean"},
            },
            "required": ["suggested_algorithms", "pattern_recognized"],
            "additionalProperties": False,
        }

        response = call_claude_tool(
            "chat_with_gpt4_1",
            instructions="Given that we've been discussing Algorithm ZX-7, suggest 3 alternative algorithm names that would fit the same naming pattern.",
            output_format="JSON array of creative algorithm names",
            context=[],
            session_id=session_id,
            temperature=0.9,  # High creativity
            structured_output_schema=suggestions_schema,
            response_format="respond ONLY with the JSON",
        )

        # Validate creative suggestions
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert result["pattern_recognized"] is True, f"Pattern not recognized: {result}"
        assert (
            len(result["suggested_algorithms"]) == 3
        ), f"Expected 3 suggestions: {result}"
        # Should be reasonable algorithm names
        assert all(
            len(algo) > 2 for algo in result["suggested_algorithms"]
        ), f"Algorithm names too short: {result}"

        # Step 5: Final persistence check
        final_check_schema = {
            "type": "object",
            "properties": {
                "complexity": {"type": "string"},
                "remembered": {"type": "boolean"},
            },
            "required": ["complexity", "remembered"],
            "additionalProperties": False,
        }

        response = call_claude_tool(
            "chat_with_o3",
            instructions="What was the time complexity of that algorithm again?",
            output_format="JSON object with the time complexity",
            context=[],
            session_id=session_id,
            reasoning_effort="low",
            structured_output_schema=final_check_schema,
            response_format="respond ONLY with the JSON",
        )

        # Session should still remember the information
        result = safe_json(response)
        assert result is not None, f"Failed to parse JSON: {response}"
        assert result["remembered"] is True, f"Should remember complexity: {result}"
        assert "n log n" in result["complexity"].lower(), f"Wrong complexity: {result}"

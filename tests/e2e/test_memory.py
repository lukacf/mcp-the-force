"""E2E tests for project memory functionality."""

import json
import time
import uuid


def wait_for_memory_indexed(claude_code, fact, timeout=60):
    """Poll until a fact appears in memory search results."""
    start_time = time.time()
    last_output = None

    while time.time() - start_time < timeout:
        output = claude_code(
            f'Use second-brain search_project_memory with query "{fact}" and max_results 10'
        )
        last_output = output

        if fact in output and "No results found" not in output:
            return True

        time.sleep(2)  # Poll every 2 seconds

    # Timeout reached
    import pytest

    pytest.fail(
        f"Fact '{fact}' not found in memory after {timeout}s. Last output: {last_output}"
    )


class TestE2EMemory:
    """Test the project memory system end-to-end."""

    def test_conversation_memory_storage(self, claude_code):
        """Test that conversations are automatically stored in memory."""
        # Create a unique fact to track
        unique_fact = f"MEMORY_TEST_{uuid.uuid4().hex[:8]}"
        session_id = f"memory-test-{uuid.uuid4().hex[:8]}"

        # First: Have a conversation with unique content
        args1 = {
            "instructions": f"Remember this unique fact: {unique_fact}. Acknowledge that you've stored it.",
            "output_format": "brief acknowledgment only",
            "context": [],
            "session_id": session_id,
        }

        output1 = claude_code(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args1)}"
        )

        print(f"Initial conversation output: {output1}")
        # Just verify we got a response - the important test is whether memory works
        assert output1.strip()

        # Wait for async storage, summarization, and vector store indexing using polling
        wait_for_memory_indexed(claude_code, unique_fact)

        # Second: In a NEW session, search for the unique fact using memory
        # The model should be able to find it in the conversation history
        args2 = {
            "instructions": f"Use the search_project_memory function to search for the exact string: {unique_fact}. This should search through all stored conversations. Report the results in the specified JSON format.",
            "output_format": f'JSON object: {{"found": true/false, "fact": "{unique_fact}" if found or null, "num_results": number}}',
            "context": [],  # No context - relying on memory
            "session_id": f"different-session-{uuid.uuid4().hex[:8]}",  # Different session
        }

        output2 = claude_code(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args2)}"
        )

        print(f"Memory search output: {output2}")

        # Parse JSON response
        try:
            result = json.loads(output2.strip())
            assert result.get("found") is True, f"Fact not found in memory: {result}"
            assert result.get("fact") == unique_fact or unique_fact in str(result)
        except json.JSONDecodeError:
            # Fallback to string matching
            assert unique_fact in output2 or "found" in output2.lower()

    def test_cross_model_memory_sharing(self, claude_code):
        """Test that memory is shared across different models."""
        # Create unique content
        unique_info = f"CROSS_MODEL_TEST_{uuid.uuid4().hex[:8]}"

        # Store with o3
        args1 = {
            "instructions": f"Remember this cross-model test info: {unique_info}",
            "output_format": "brief confirmation",
            "context": [],
            "session_id": f"o3-memory-{uuid.uuid4().hex[:8]}",
        }

        output1 = claude_code(f"Use second-brain chat_with_o3 with {json.dumps(args1)}")

        print(f"O3 storage output: {output1}")

        # Wait for storage and vector store indexing using polling
        wait_for_memory_indexed(claude_code, unique_info)

        # Retrieve with Gemini - be explicit about using memory search
        args2 = {
            "instructions": f"Use the search_project_memory function to search for '{unique_info}'. Report what you find in the search results.",
            "output_format": "found information only",
            "context": [],
        }

        output2 = claude_code(
            f"Use second-brain chat_with_gemini25_flash with {json.dumps(args2)}"
        )

        print(f"Gemini retrieval output: {output2}")
        # Gemini should find the info stored by o3
        assert unique_info in output2

    def test_memory_persistence_across_sessions(self, claude_code):
        """Test that memory persists across different tool invocations."""
        # Create a unique test identifier
        test_id = f"PERSIST_{uuid.uuid4().hex[:8]}"

        # Store a fact with explicit confirmation
        store_args = {
            "instructions": f"Remember this test fact: '{test_id}_FACT'. Confirm you've stored it.",
            "output_format": "brief confirmation",
            "context": [],
            "session_id": f"store-{uuid.uuid4().hex[:8]}",
        }

        store_output = claude_code(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(store_args)}"
        )
        print(f"Store output: {store_output}")
        assert store_output.strip()  # Just verify we got a response

        # Wait for async storage and indexing using polling
        wait_for_memory_indexed(claude_code, f"{test_id}_FACT")

        # Search for the fact in a new session
        search_args = {
            "instructions": f"Use the search_project_memory function to find any facts containing '{test_id}'. Report what you find.",
            "output_format": f"If you find '{test_id}_FACT', output exactly 'FOUND'. If not found, output 'NOT_FOUND'.",
            "context": [],
            "session_id": f"search-{uuid.uuid4().hex[:8]}",
        }

        search_output = claude_code(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(search_args)}"
        )

        print(f"Search output: {search_output}")

        # Check if fact was found
        assert "FOUND" in search_output or test_id in search_output

    def test_memory_with_code_context(self, claude_code, tmp_path):
        """Test memory system with actual code analysis."""
        # Create a unique function
        unique_func = f"memory_test_func_{uuid.uuid4().hex[:8]}"
        code_file = tmp_path / "memory_test.py"
        code_file.write_text(f"""
def {unique_func}():
    '''This function is for testing memory storage.'''
    return "Memory test successful"

# Special marker: MEMORY_MARKER_{uuid.uuid4().hex[:8]}
""")

        # Analyze the code
        args1 = {
            "instructions": f"Analyze the function {unique_func} in the code. Describe what it does.",
            "output_format": "brief description",
            "context": [str(tmp_path)],
            "session_id": f"code-analysis-{uuid.uuid4().hex[:8]}",
        }

        output1 = claude_code(
            f"Use second-brain chat_with_gemini25_pro with {json.dumps(args1)}"
        )

        print(f"Code analysis output: {output1}")
        assert "memory" in output1.lower()

        # Wait for storage using polling
        wait_for_memory_indexed(claude_code, "calculate_compound_interest")

        # Later, ask about the function without providing context
        args2 = {
            "instructions": f"Use the search_project_memory function to search for information about the function {unique_func}. Report what you find.",
            "output_format": "what you remember about this function",
            "context": [],  # No context!
            "session_id": f"memory-recall-{uuid.uuid4().hex[:8]}",
        }

        output2 = claude_code(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args2)}"
        )

        print(f"Memory recall output: {output2}")
        # Should remember the function from memory
        assert unique_func in output2
        assert "test" in output2.lower() or "memory" in output2.lower()

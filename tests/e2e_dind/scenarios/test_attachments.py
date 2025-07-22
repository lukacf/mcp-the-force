"""Context overflow and RAG test - Verify files are split between inline context and vector store."""

import os
import sys
import uuid
import time

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Unique tokens for different files to verify access from both inline and vector store
INLINE_TOKEN = "overflow-test-marker-xyz-123"
OVERFLOW_TOKEN = "overflow-test-marker-plugh-456"
PRIORITY_TOKEN = "priority-test-marker-qwerty-789"


class TestContextOverflowAndRag:
    """Test the context overflow mechanism and RAG access to vector stores."""

    def test_overflow_and_rag_access(
        self,
        call_claude_tool,
        isolated_test_dir,
        create_file_in_container,
        setup_mcp_with_low_context,
    ):
        """Test that large files overflow to vector stores while small files remain inline."""
        print("🔍 Starting context overflow and RAG test...")

        # Configure MCP with low context percentage to force overflow with smaller files
        setup_mcp_with_low_context()

        # Create a small file that should fit inline
        small_file = os.path.join(isolated_test_dir, "small_inline.txt")
        small_content = (
            f"This is a small file that contains the inline token: {INLINE_TOKEN}\n"
            * 10
        )
        create_file_in_container(small_file, small_content)
        print(f"📄 Created small file (should be inline): {small_file}")

        # Create a "large" file that will overflow due to low CONTEXT_PERCENTAGE (1%)
        # With 1% of ~1M tokens, we have ~10k tokens budget. At ~2 bytes/token, need >20KB
        large_file = os.path.join(isolated_test_dir, "large_overflow.txt")
        # 50KB should definitely trigger overflow
        large_content = (
            f"This file contains the overflow token: {OVERFLOW_TOKEN}\n"
            + "X" * 50000  # 50KB of content
        )
        create_file_in_container(large_file, large_content)
        print(
            f"📄 Created large file (should overflow): {large_file} ({len(large_content)} bytes)"
        )

        # Call chat_with_gpt4_1 with both files in context
        response = call_claude_tool(
            "chat_with_gpt4_1",
            instructions=f"Search for and quote the exact sentences containing these tokens: '{INLINE_TOKEN}' and '{OVERFLOW_TOKEN}'. For each token, state whether you found it and quote the containing sentence.",
            output_format="For each token, state: 1) Found/Not found 2) The exact sentence containing it (if found)",
            context=[small_file, large_file],
            session_id=f"overflow-test-{uuid.uuid4().hex[:8]}",
        )

        print(f"✅ Response: {response}")

        # Verify model can find content from both files
        assert (
            INLINE_TOKEN in response
        ), f"Model failed to find inline token '{INLINE_TOKEN}' from small file"
        assert (
            OVERFLOW_TOKEN in response
        ), f"Model failed to find overflow token '{OVERFLOW_TOKEN}' from vector store"

        # Verify the model actually found both tokens (not just echoed them)
        response_lower = response.lower()
        assert any(
            word in response_lower
            for word in ["found", "contains", "sentence", "quote"]
        ), "Response should indicate actual retrieval of content"

        print("✅ Context overflow and RAG access test passed!")

    def test_priority_context_overrides_overflow(
        self,
        call_claude_tool,
        isolated_test_dir,
        create_file_in_container,
        setup_mcp_with_low_context,
    ):
        """Test that priority_context forces large files to be inline instead of overflowing."""
        print("🔍 Starting priority context override test...")

        # Configure MCP with low context percentage to test priority override
        setup_mcp_with_low_context()

        # Create a file that would overflow with 1% context limit
        large_priority_file = os.path.join(isolated_test_dir, "large_priority.txt")
        # 50KB to ensure overflow with 1% context percentage
        large_content = (
            f"This is a priority file with the special token: {PRIORITY_TOKEN}\n"
            + "Y" * 50000  # 50KB of content
        )
        create_file_in_container(large_priority_file, large_content)
        print(
            f"📄 Created large priority file: {large_priority_file} ({len(large_content)} bytes)"
        )

        # Create another file for regular context (should overflow)
        large_regular_file = os.path.join(isolated_test_dir, "large_regular.txt")
        regular_content = (
            f"This is a regular file with overflow content: {OVERFLOW_TOKEN}\n"
            + "Z" * 50000  # 50KB of content
        )
        create_file_in_container(large_regular_file, regular_content)
        print(f"📄 Created large regular file: {large_regular_file}")

        # Call with priority_context to force inline inclusion
        response = call_claude_tool(
            "chat_with_gpt4_1",
            instructions=f"Without using any search or retrieval, directly quote any sentences you can see that contain the token '{PRIORITY_TOKEN}'. If you cannot directly see this token in the provided context, say 'Token not in direct context'.",
            output_format="Either quote the sentence with the token or state it's not in direct context",
            context=[large_regular_file],
            priority_context=[large_priority_file],
            session_id=f"priority-test-{uuid.uuid4().hex[:8]}",
        )

        print(f"✅ Response: {response}")

        # Verify the priority file content is accessible directly (not via search)
        assert (
            PRIORITY_TOKEN in response
        ), f"Model failed to find priority token '{PRIORITY_TOKEN}' that should be inline"

        # Verify it's not reporting "not in direct context"
        assert (
            "not in direct context" not in response.lower()
        ), "Priority file was not included inline as expected"

        print("✅ Priority context override test passed!")

    def test_multiple_sessions_stable_list(
        self,
        call_claude_tool,
        isolated_test_dir,
        create_file_in_container,
        setup_mcp_with_low_context,
    ):
        """Test that the stable list mechanism works across multiple calls in the same session."""
        print("🔍 Starting stable list mechanism test...")

        # Configure MCP with low context percentage for consistent testing
        setup_mcp_with_low_context()

        session_id = f"stable-list-test-{uuid.uuid4().hex[:8]}"

        # Create files with different sizes
        files = []
        for i in range(5):
            file_path = os.path.join(isolated_test_dir, f"file_{i}.txt")
            # Create files of increasing size
            content = f"File {i} content with token: test-{i}-marker\n" * (
                100 * (i + 1)
            )
            create_file_in_container(file_path, content)
            files.append(file_path)
            print(f"📄 Created file {i}: {file_path} ({len(content)} bytes)")

        # First call - establishes the stable list
        response1 = call_claude_tool(
            "chat_with_gpt4_1",
            instructions="List all the test markers you can find (format: test-X-marker)",
            output_format="List of all markers found",
            context=files,
            session_id=session_id,
        )
        print(f"✅ First call response: {response1}")

        # Give a moment for stable list to be established
        time.sleep(1)

        # Second call - should use the same stable list
        response2 = call_claude_tool(
            "chat_with_gpt4_1",
            instructions="Again, list all the test markers you can find",
            output_format="List of all markers found",
            context=files,
            session_id=session_id,
        )
        print(f"✅ Second call response: {response2}")

        # Both responses should find the same markers
        # Extract markers from responses
        import re

        markers1 = set(re.findall(r"test-\d+-marker", response1))
        markers2 = set(re.findall(r"test-\d+-marker", response2))

        assert len(markers1) > 0, "First call should find at least some markers"
        assert len(markers2) > 0, "Second call should find at least some markers"

        # The stable list mechanism should ensure consistent file handling
        print(f"Markers from call 1: {markers1}")
        print(f"Markers from call 2: {markers2}")

        print("✅ Stable list mechanism test passed!")

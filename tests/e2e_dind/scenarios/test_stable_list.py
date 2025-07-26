"""Stable-inline list feature tests - multi-turn scenarios for context management."""

import os
import sys
import time

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Unique markers for test verification (avoid "token" which triggers redaction)
MARKER_SMALL_FILE = "stable-list-small-xyzzy-42"
MARKER_LARGE_FILE = "stable-list-large-quux-99"
MARKER_CONTEXT_1 = "stable-list-context1-foo-123"
MARKER_CONTEXT_2 = "stable-list-context2-bar-456"
MARKER_MODIFIED_FILE = "stable-list-modified-baz-789"


class TestStableInlineList:
    """Test the stable-inline list feature for context overflow management."""

    def test_initial_split_and_multimodal_access(
        self, call_claude_tool, isolated_test_dir, create_file_in_container
    ):
        """
        Test that files are correctly split between inline and vector store on first call.
        This test validates that all files are passed via the 'context' parameter.
        """
        print("🔍 Testing initial split and multi-modal access...")

        # Create a small file that will fit in inline context
        small_file = os.path.join(isolated_test_dir, "small_file.txt")
        small_content = (
            f"This is a small file.\nThe secret token is: {MARKER_SMALL_FILE}\n"
        )
        create_file_in_container(small_file, small_content)

        # Create a file that will overflow due to 1% context limit
        large_file = os.path.join(isolated_test_dir, "large_file.txt")
        large_content = "This file will overflow with 1% context limit.\n" * 30
        large_content += f"\nThe large file token is: {MARKER_LARGE_FILE}\n"
        large_content += "More content to ensure overflow.\n" * 30
        create_file_in_container(large_file, large_content)

        # Call with context that will trigger overflow
        response = call_claude_tool(
            "chat_with_gpt41",
            instructions=(
                f"Search all provided files for the sentence containing the token '{MARKER_SMALL_FILE}'. "
                f"You will need to use your search tool to find a token in a different file: '{MARKER_LARGE_FILE}'. "
                "Quote the exact sentences containing both tokens."
            ),
            output_format="List each token found with the quoted sentence containing it.",
            context=[small_file, large_file],  # All files are now in the context list
            priority_context=[],
            session_id="stable-list-test-split",
        )
        print(f"✅ First response: {response}")

        # Verify both tokens are found, proving the model can access both inline and overflowed (vector store) files
        assert MARKER_SMALL_FILE in response, "Failed to find token from inline context"
        assert MARKER_LARGE_FILE in response, (
            "Failed to find token from overflow file in vector store"
        )
        print(
            "✅ Initial split test passed - model accessed both inline and vector store content!"
        )

    def test_context_deduplication_and_statefulness(
        self, call_claude_tool, isolated_test_dir, create_file_in_container
    ):
        """
        Test that unchanged files are not resent in subsequent calls.
        This test validates that all files are passed via the 'context' parameter.
        """
        print("🔍 Testing context deduplication and statefulness...")

        # Create initial files
        unchanged_file = os.path.join(isolated_test_dir, "unchanged_file.txt")
        unchanged_content = f"This is a file that will persist across calls.\nThe token is: {MARKER_SMALL_FILE}\n"
        create_file_in_container(unchanged_file, unchanged_content)

        context1_file = os.path.join(isolated_test_dir, "context1.txt")
        context1_content = f"This is the first context file.\nFirst context token: {MARKER_CONTEXT_1}\n"
        create_file_in_container(context1_file, context1_content)

        # First call - establish the stable list and send initial files
        response1 = call_claude_tool(
            "chat_with_gpt41",
            instructions=f"Find and quote the sentences containing the tokens '{MARKER_SMALL_FILE}' and '{MARKER_CONTEXT_1}'.",
            output_format="Quote the exact sentences containing the tokens.",
            context=[unchanged_file, context1_file],
            priority_context=[],
            session_id="stable-list-test-dedup",
        )
        print(f"✅ First response: {response1}")
        assert MARKER_SMALL_FILE in response1, (
            f"Failed to find initial token in first call. Response: {response1}"
        )
        assert MARKER_CONTEXT_1 in response1, (
            f"Failed to find context token in first call. Response: {response1}"
        )

        # Second call - provide the unchanged file and a new file
        # The server should detect that 'unchanged_file' was already sent and not resend it
        context2_file = os.path.join(isolated_test_dir, "context2.txt")
        context2_content = f"This is the second context file.\nSecond context token: {MARKER_CONTEXT_2}\n"
        create_file_in_container(context2_file, context2_content)

        response2 = call_claude_tool(
            "chat_with_gpt41",
            instructions=(
                f"In this multi-turn conversation:\n"
                f"1. Confirm you remember the token '{MARKER_SMALL_FILE}' from our previous exchange.\n"
                f"2. Now find and quote the sentence containing the new token '{MARKER_CONTEXT_2}' from the newly provided file."
            ),
            output_format=(
                "1. State the first token you remember.\n"
                "2. Quote the sentence containing the new token."
            ),
            context=[unchanged_file, context2_file],  # Provide unchanged and new file
            priority_context=[],
            session_id="stable-list-test-dedup",  # Same session
        )
        print(f"✅ Second response: {response2}")

        # Verify the model recalls the first token (from memory/session) and finds the new token
        assert MARKER_SMALL_FILE in response2, (
            "Failed to recall token from previous turn"
        )
        assert MARKER_CONTEXT_2 in response2, "Failed to find new context token"
        print(
            "✅ Deduplication test passed - model remembered context without resending!"
        )

    def test_changed_file_detection(
        self, call_claude_tool, isolated_test_dir, create_file_in_container, stack
    ):
        """Test that modified files are detected and resent."""
        print("🔍 Testing changed file detection...")

        # Create initial file
        changing_file = os.path.join(isolated_test_dir, "changing_file.txt")
        original_content = f"Original content.\nOriginal token: {MARKER_SMALL_FILE}\n"
        create_file_in_container(changing_file, original_content)

        # First call - establish baseline
        response1 = call_claude_tool(
            "chat_with_gpt41",
            instructions=f"Find and quote the sentence containing token '{MARKER_SMALL_FILE}'.",
            output_format="Quote the exact sentence containing the token.",
            context=[changing_file],
            priority_context=[],
            session_id="stable-list-test-change",
        )
        print(f"✅ First response: {response1}")
        assert MARKER_SMALL_FILE in response1, "Failed to find original token"

        # Modify the file - use os.utime to ensure mtime changes without sleep
        modified_content = f"Modified content with different size.\nModified token: {MARKER_MODIFIED_FILE}\nExtra line to ensure size difference.\n"
        create_file_in_container(changing_file, modified_content)

        # Explicitly update the modification time to ensure change detection
        # Since we're running inside the container, we need to use the stack to update mtime
        future_time = time.time() + 10  # Set mtime 10 seconds in the future
        stack.exec_in_container(
            [
                "touch",
                "-t",
                time.strftime("%Y%m%d%H%M.%S", time.localtime(future_time)),
                changing_file,
            ],
            "test-runner",
        )

        # Second call - should detect the change and resend the file
        response2 = call_claude_tool(
            "chat_with_gpt41",
            instructions=f"The file has changed. Find and quote the sentence containing the new token '{MARKER_MODIFIED_FILE}'.",
            output_format="Quote the exact sentence containing the token.",
            context=[changing_file],  # Same file path, but content is modified
            priority_context=[],
            session_id="stable-list-test-change",  # Same session
        )
        print(f"✅ Second response: {response2}")

        # Verify the new token is found, proving the modified file was resent and read
        assert MARKER_MODIFIED_FILE in response2, (
            "Failed to find modified token - file was not resent"
        )
        assert MARKER_SMALL_FILE not in response2, (
            "Old token found - file change not detected"
        )
        print("✅ Change detection test passed - modified file was resent!")

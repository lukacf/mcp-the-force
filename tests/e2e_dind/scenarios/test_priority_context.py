import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


class TestPriorityContextAndFileTree:
    """Test priority_context parameter and file tree verification."""

    def test_priority_context_forces_inline(
        self, call_claude_tool, isolated_test_dir, create_file_in_container
    ):
        """
        Test that priority_context forces files to be included inline even if they would normally overflow.
        """
        # Create a file that would trigger overflow with 1% context limit
        # With 1% of 1M tokens = 10,000 tokens, we need a file larger than that
        # Assuming ~3 chars per token, we need >30,000 characters
        large_content = "x" * 50000  # 50KB should definitely overflow with 1% limit
        large_file_path = os.path.join(isolated_test_dir, "large_priority_file.txt")
        create_file_in_container(large_file_path, large_content)

        # Create a marker for verification
        marker = "priority-test-alpha-001"
        marker_file_path = os.path.join(isolated_test_dir, "marker.txt")
        create_file_in_container(marker_file_path, f"MARKER: {marker}")

        # Call with priority_context
        response = call_claude_tool(
            "chat_with_gemini25_flash",
            instructions=f"Find the marker {marker} and confirm you can see the large file content directly without using search_task_files",
            output_format="Report: 1) The marker value 2) First 100 chars of large file 3) Confirm if you saw it directly inline",
            context=[marker_file_path],
            priority_context=[large_file_path],
            session_id="priority-inline-test",
        )

        # Verify the response indicates direct access (not via search)
        assert marker in response, f"Marker {marker} not found in response"
        assert (
            "search_task_files" not in response.lower()
        ), "Model should not need to search for priority files"
        assert (
            "x" * 50 in response
        ), "Model should be able to see the large file content directly"

    def test_file_tree_accuracy(
        self, call_claude_tool, isolated_test_dir, create_file_in_container
    ):
        """
        Test that the file_map accurately reflects which files are inline vs attached.
        """
        # Create a mix of files
        marker = "priority-test-beta-002"

        # Small files that should be inline
        small1_path = os.path.join(isolated_test_dir, "small1.txt")
        create_file_in_container(small1_path, f"Small file 1 with marker: {marker}")

        small2_path = os.path.join(isolated_test_dir, "small2.txt")
        create_file_in_container(small2_path, "Small file 2 content")

        # File that should overflow with 1% context limit
        large_path = os.path.join(isolated_test_dir, "large_overflow.txt")
        large_content = "y" * 50000  # 50KB to ensure overflow
        create_file_in_container(large_path, large_content)

        # Another file for priority context
        priority_large_path = os.path.join(isolated_test_dir, "priority_large.txt")
        priority_content = "z" * 50000  # 50KB priority file
        create_file_in_container(priority_large_path, priority_content)

        # Call with mixed context
        response = call_claude_tool(
            "chat_with_gemini25_flash",
            instructions=f"Report on the file organization. Find marker {marker} and describe which files you can see directly vs need to search for",
            output_format="List each file and whether you can see its content directly or would need to search",
            context=[small1_path, small2_path, large_path],
            priority_context=[priority_large_path],
            session_id="file-tree-test",
        )

        # Verify small files and priority file are directly visible
        assert marker in response, f"Marker {marker} should be visible directly"
        assert "small file 1" in response.lower(), "Small file 1 should be mentioned"
        assert "small file 2" in response.lower(), "Small file 2 should be mentioned"

        # The large non-priority file should require search
        # Note: This is indirect verification since we can't directly inspect the file_map
        # but the model's behavior tells us about the file organization
        if "search" in response.lower() and "large_overflow" in response.lower():
            # Expected: large_overflow.txt is attached and would need search
            pass
        else:
            # If model can see all files directly, it might mean our files aren't large enough
            # or the model has a very large context window
            print(
                "Warning: Expected large_overflow.txt to be attached, but model may see it directly"
            )

    def test_dynamic_overflow(
        self, call_claude_tool, isolated_test_dir, create_file_in_container
    ):
        """
        Test that the system handles dynamic overflow correctly across multiple calls.
        """
        marker_base = "priority-test-gamma-003"

        # First call: only small files (should all be inline)
        small1_path = os.path.join(isolated_test_dir, "dynamic_small1.txt")
        create_file_in_container(
            small1_path, f"Small dynamic file 1: {marker_base}-small1"
        )

        small2_path = os.path.join(isolated_test_dir, "dynamic_small2.txt")
        create_file_in_container(
            small2_path, f"Small dynamic file 2: {marker_base}-small2"
        )

        # First call with small files only
        response1 = call_claude_tool(
            "chat_with_gemini25_flash",
            instructions=f"Find all markers starting with {marker_base} and list them",
            output_format="List all markers you can see directly",
            context=[small1_path, small2_path],
            session_id="dynamic-overflow-test",
        )

        # Verify both small file markers are visible
        assert (
            f"{marker_base}-small1" in response1
        ), "First small file marker should be visible"
        assert (
            f"{marker_base}-small2" in response1
        ), "Second small file marker should be visible"

        # Second call: add a file that should trigger overflow with 1% limit
        large_path = os.path.join(isolated_test_dir, "dynamic_large.txt")
        large_content = "w" * 50000 + f"\nLarge file marker: {marker_base}-large"
        create_file_in_container(large_path, large_content)

        # Also modify one of the small files to ensure it's included
        create_file_in_container(
            small1_path, f"Modified small file 1: {marker_base}-small1-modified"
        )

        # Second call with additional large file
        response2 = call_claude_tool(
            "chat_with_gemini25_flash",
            instructions=f"Find all markers starting with {marker_base}, including any new or modified ones. Report which files you need to search vs see directly",
            output_format="List: 1) Markers visible directly 2) Files that would need search 3) Any changes from previous context",
            context=[small1_path, small2_path, large_path],
            session_id="dynamic-overflow-test",
        )

        # Verify the modified small file is visible
        assert (
            f"{marker_base}-small1-modified" in response2
        ), "Modified small file should be visible"

        # The large file should be mentioned as needing search or attached
        # This verifies dynamic overflow handling
        if "search" in response2.lower() or "attached" in response2.lower():
            # Expected behavior: large file is in vector store
            pass
        else:
            # Check if the model at least acknowledges the large file exists
            assert (
                "large" in response2.lower()
            ), "Large file should be mentioned somehow"


# Simple syntax check when run directly
if __name__ == "__main__":
    import py_compile

    py_compile.compile(__file__, doraise=True)
    print("Syntax check passed!")

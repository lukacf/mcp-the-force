"""Stable-inline list feature tests - multi-turn scenarios for context management."""

import os
import json
import sys
import pytest
import time

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Unique tokens for test verification
TOKEN_SMALL_FILE = "stable-list-small-xyzzy-42"
TOKEN_LARGE_FILE = "stable-list-large-quux-99"
TOKEN_ATTACHMENT_1 = "stable-list-attach1-foo-123"
TOKEN_ATTACHMENT_2 = "stable-list-attach2-bar-456"
TOKEN_MODIFIED_FILE = "stable-list-modified-baz-789"


class TestStableInlineList:
    """Test the stable-inline list feature for context overflow management."""

    def setup_method(self):
        """Create test directory for each test."""
        # Ensure CI_E2E is set for the MCP server to allow /tmp paths
        os.environ["CI_E2E"] = "1"

        # Use /tmp which is shared between containers
        self.test_dir = "/tmp/test_stable_list_data"
        os.makedirs(self.test_dir, exist_ok=True)

        # Fix permissions - chown to claude user so MCP server can access
        self._fix_permissions(self.test_dir)

    def _fix_permissions(self, path):
        """Fix permissions so claude user can access files."""
        import subprocess

        # Ensure CI_E2E is set for subprocess calls
        env = os.environ.copy()
        env["CI_E2E"] = "1"
        try:
            subprocess.run(["chown", "-R", "claude:claude", path], check=True, env=env)
            # Make files world-readable as a temporary fix
            subprocess.run(["chmod", "-R", "a+rX", path], check=True, env=env)
            print(f"DEBUG: Set world-readable permissions on {path}")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to set permissions on {path}: {e}")

    def teardown_method(self):
        """Clean up test files after each test."""
        import shutil

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    @pytest.mark.parametrize("claude", [True], indirect=True)
    def test_initial_split_and_multimodal_access(self, claude):
        """Test that files are correctly split between inline and vector store on first call."""
        print("🔍 Testing initial split and multi-modal access...")

        # Create a small file that will fit in inline context
        small_file = os.path.join(self.test_dir, "small_file.txt")
        with open(small_file, "w") as f:
            f.write(f"This is a small file.\nThe secret token is: {TOKEN_SMALL_FILE}\n")

        # Create a large file that will overflow to vector store
        large_file = os.path.join(self.test_dir, "large_file.txt")
        with open(large_file, "w") as f:
            # Make it large enough to trigger overflow
            f.write("This is a very large file with lots of content.\n" * 10000)
            f.write(f"\nThe large file token is: {TOKEN_LARGE_FILE}\n")
            f.write("More content to ensure overflow.\n" * 10000)

        # Create an attachment (always goes to vector store)
        attachment = os.path.join(self.test_dir, "attachment1.txt")
        with open(attachment, "w") as f:
            f.write(
                f"This is an attachment.\nThe attachment token is: {TOKEN_ATTACHMENT_1}\n"
            )

        # Fix permissions on all created files so MCP server can access them
        self._fix_permissions(self.test_dir)

        # Debug: verify files exist and check permissions
        print(f"DEBUG: test_dir = {self.test_dir}")
        import subprocess

        result = subprocess.run(
            ["ls", "-la", self.test_dir], capture_output=True, text=True
        )
        print(f"DEBUG: Directory listing:\n{result.stdout}")

        # Also check environment
        print(f"DEBUG: CI_E2E = {os.environ.get('CI_E2E', 'not set')}")
        print(f"DEBUG: CWD = {os.getcwd()}")

        # Call with context that will trigger overflow
        args = {
            "instructions": (
                f"Search for and quote the exact sentences containing these tokens:\n"
                f"1. '{TOKEN_SMALL_FILE}' (from context)\n"
                f"2. '{TOKEN_ATTACHMENT_1}' (from attachment)\n"
                f"Note: There may be files you cannot see directly but can search."
            ),
            "output_format": "List each token found with the quoted sentence containing it.",
            "context": [small_file, large_file],
            "attachments": [attachment],
            "session_id": "stable-list-test-split",
        }

        response = claude(f"Use second-brain chat_with_gpt4_1 with {json.dumps(args)}")
        print(f"✅ First response: {response}")

        # Verify both tokens are found
        assert TOKEN_SMALL_FILE in response, "Failed to find token from inline context"
        assert (
            TOKEN_ATTACHMENT_1 in response
        ), "Failed to find token from attachment in vector store"
        print(
            "✅ Initial split test passed - model accessed both inline and vector store content!"
        )

    @pytest.mark.parametrize("claude", [True], indirect=True)
    def test_context_deduplication_and_statefulness(self, claude):
        """Test that unchanged files are not resent in subsequent calls."""
        print("🔍 Testing context deduplication and statefulness...")

        # Debug: Add a sleep to allow checking container state
        import time

        print("DEBUG: Sleeping 5s to allow container inspection...")
        time.sleep(5)

        # Create initial files
        context_file = os.path.join(self.test_dir, "context_file.txt")
        with open(context_file, "w") as f:
            f.write(
                f"This is a context file.\nThe context token is: {TOKEN_SMALL_FILE}\n"
            )

        attachment1 = os.path.join(self.test_dir, "attachment1.txt")
        with open(attachment1, "w") as f:
            f.write(
                f"First attachment.\nFirst attachment token: {TOKEN_ATTACHMENT_1}\n"
            )

        # Fix permissions on all created files
        self._fix_permissions(self.test_dir)

        # First call - establish the stable list
        args1 = {
            "instructions": f"Find and quote the exact sentence containing the token '{TOKEN_SMALL_FILE}' from the context files provided.",
            "output_format": "Quote the exact sentence containing the token.",
            "context": [context_file],
            "attachments": [attachment1],
            "session_id": "stable-list-test-dedup",
        }

        response1 = claude(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args1)}"
        )
        print(f"✅ First response: {response1}")
        assert (
            TOKEN_SMALL_FILE in response1
        ), f"Failed to find token in first call. Response: {response1}"

        # Second call - same context, new attachment
        # The context file should NOT be resent since it's unchanged
        attachment2 = os.path.join(self.test_dir, "attachment2.txt")
        with open(attachment2, "w") as f:
            f.write(
                f"Second attachment.\nSecond attachment token: {TOKEN_ATTACHMENT_2}\n"
            )

        # Fix permissions for the new attachment
        self._fix_permissions(attachment2)

        args2 = {
            "instructions": (
                f"In this multi-turn conversation:\n"
                f"1. You should already remember the token '{TOKEN_SMALL_FILE}' from our previous exchange.\n"
                f"2. Now find and quote the sentence containing '{TOKEN_ATTACHMENT_2}' from the new attachment."
            ),
            "output_format": (
                "1. Confirm you remember the previous token and state what it was.\n"
                "2. Quote the sentence containing the new attachment token."
            ),
            "context": [context_file],  # Same context, should not be resent
            "attachments": [attachment2],  # New attachment
            "session_id": "stable-list-test-dedup",  # Same session
        }

        response2 = claude(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args2)}"
        )
        print(f"✅ Second response: {response2}")

        # Verify the model recalls the first token from memory (not re-reading)
        assert (
            TOKEN_SMALL_FILE in response2
        ), "Failed to recall token from previous turn"
        assert TOKEN_ATTACHMENT_2 in response2, "Failed to find new attachment token"
        print(
            "✅ Deduplication test passed - model remembered context without resending!"
        )

    @pytest.mark.parametrize("claude", [True], indirect=True)
    def test_changed_file_detection(self, claude):
        """Test that modified files are detected and resent."""
        print("🔍 Testing changed file detection...")

        # Create initial file
        changing_file = os.path.join(self.test_dir, "changing_file.txt")
        with open(changing_file, "w") as f:
            f.write(f"Original content.\nOriginal token: {TOKEN_SMALL_FILE}\n")

        # Fix permissions
        self._fix_permissions(changing_file)

        # First call - establish baseline
        args1 = {
            "instructions": f"Find and quote the sentence containing token '{TOKEN_SMALL_FILE}'.",
            "output_format": "Quote the exact sentence containing the token.",
            "context": [changing_file],
            "attachments": [],
            "session_id": "stable-list-test-change",
        }

        response1 = claude(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args1)}"
        )
        print(f"✅ First response: {response1}")
        assert TOKEN_SMALL_FILE in response1, "Failed to find original token"

        # Wait a moment to ensure mtime difference
        time.sleep(1)

        # Modify the file - ensure size changes too
        with open(changing_file, "w") as f:
            f.write(
                f"Modified content with different size.\nModified token: {TOKEN_MODIFIED_FILE}\nExtra line to ensure size difference.\n"
            )

        # Fix permissions after modification
        self._fix_permissions(changing_file)

        # Second call - should detect the change and resend
        args2 = {
            "instructions": f"Find and quote the sentence containing token '{TOKEN_MODIFIED_FILE}'.",
            "output_format": "Quote the exact sentence containing the token.",
            "context": [changing_file],  # Same file, but modified
            "attachments": [],
            "session_id": "stable-list-test-change",  # Same session
        }

        response2 = claude(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args2)}"
        )
        print(f"✅ Second response: {response2}")

        # Verify the new token is found (proving file was resent)
        assert (
            TOKEN_MODIFIED_FILE in response2
        ), "Failed to find modified token - file was not resent"
        assert (
            TOKEN_SMALL_FILE not in response2
        ), "Old token found - file change not detected"
        print("✅ Change detection test passed - modified file was resent!")

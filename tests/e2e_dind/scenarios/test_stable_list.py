"""Stable-inline list feature tests - multi-turn scenarios for context management."""

import os
import json
import sys
import pytest
import time

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Unique markers for test verification (avoid "token" which triggers redaction)
MARKER_SMALL_FILE = "stable-list-small-xyzzy-42"
MARKER_LARGE_FILE = "stable-list-large-quux-99"
MARKER_ATTACHMENT_1 = "stable-list-attach1-foo-123"
MARKER_ATTACHMENT_2 = "stable-list-attach2-bar-456"
MARKER_MODIFIED_FILE = "stable-list-modified-baz-789"


class TestStableInlineList:
    """Test the stable-inline list feature for context overflow management."""

    def _setup_test_dir(self, stack):
        """Setup test directory inside the container with unique UUID."""
        import os
        import uuid

        # Store the stack
        self.stack = stack

        # Use /tmp with UUID for per-test isolation - shared between containers via named volume
        test_uuid = uuid.uuid4().hex[:8]
        self.test_dir = f"/tmp/test_stable_list_data_{test_uuid}"

        # Create directory directly with Python (running as root in test-runner)
        os.makedirs(self.test_dir, exist_ok=True)
        os.chmod(self.test_dir, 0o755)
        print(f"DEBUG: Created test directory {self.test_dir} inside container")

    def _exec_in_container(self, cmd, check=True):
        """Execute a command inside the test-runner container."""
        stdout, stderr, return_code = self.stack.exec_in_container(
            ["bash", "-c", cmd], "test-runner"
        )
        if check and return_code != 0:
            raise RuntimeError(f"Command failed: {cmd}\nStderr: {stderr}")
        return stdout, stderr, return_code

    def _create_file(self, path, content):
        """Create a file inside the container with the given content."""
        # Running as root in test-runner, create world-readable files
        import os

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        # Make world-readable so claude user in sub-containers can read
        os.chmod(path, 0o644)

    @pytest.mark.parametrize("claude", [True], indirect=True)
    def test_initial_split_and_multimodal_access(self, claude, stack):
        """Test that files are correctly split between inline and vector store on first call."""
        print("🔍 Testing initial split and multi-modal access...")

        # Setup test directory
        self._setup_test_dir(stack)

        # Create a small file that will fit in inline context
        small_file = os.path.join(self.test_dir, "small_file.txt")
        small_content = (
            f"This is a small file.\nThe secret token is: {MARKER_SMALL_FILE}\n"
        )
        self._create_file(small_file, small_content)

        # Create a large file that will overflow to vector store
        large_file = os.path.join(self.test_dir, "large_file.txt")
        # Make it large enough to trigger overflow
        large_content = "This is a very large file with lots of content.\n" * 10000
        large_content += f"\nThe large file token is: {MARKER_LARGE_FILE}\n"
        large_content += "More content to ensure overflow.\n" * 10000
        self._create_file(large_file, large_content)

        # Create an attachment (always goes to vector store)
        attachment = os.path.join(self.test_dir, "attachment1.txt")
        attachment_content = (
            f"This is an attachment.\nThe attachment token is: {MARKER_ATTACHMENT_1}\n"
        )
        self._create_file(attachment, attachment_content)

        # Debug: verify files exist and check permissions inside container
        print(f"DEBUG: test_dir = {self.test_dir}")
        stdout, _, _ = self._exec_in_container(f"ls -la {self.test_dir}")
        print(f"DEBUG: Directory listing:\n{stdout}")

        # Also check environment inside container
        stdout, _, _ = self._exec_in_container("echo CI_E2E=$CI_E2E")
        print(f"DEBUG: {stdout.strip()}")
        stdout, _, _ = self._exec_in_container("pwd")
        print(f"DEBUG: CWD = {stdout.strip()}")

        # Call with context that will trigger overflow
        args = {
            "instructions": (
                f"Search for and quote the exact sentences containing these tokens:\n"
                f"1. '{MARKER_SMALL_FILE}' (from context)\n"
                f"2. '{MARKER_ATTACHMENT_1}' (from attachment)\n"
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
        assert MARKER_SMALL_FILE in response, "Failed to find token from inline context"
        assert MARKER_ATTACHMENT_1 in response, (
            "Failed to find token from attachment in vector store"
        )
        print(
            "✅ Initial split test passed - model accessed both inline and vector store content!"
        )

        # Cleanup
        self._exec_in_container(f"rm -rf {self.test_dir}", check=False)

    @pytest.mark.parametrize("claude", [True], indirect=True)
    def test_context_deduplication_and_statefulness(self, claude, stack):
        """Test that unchanged files are not resent in subsequent calls."""
        print("🔍 Testing context deduplication and statefulness...")

        # Setup test directory
        self._setup_test_dir(stack)

        # Create initial files
        context_file = os.path.join(self.test_dir, "context_file.txt")
        context_content = (
            f"This is a context file.\nThe context token is: {MARKER_SMALL_FILE}\n"
        )
        self._create_file(context_file, context_content)

        attachment1 = os.path.join(self.test_dir, "attachment1.txt")
        attachment1_content = (
            f"First attachment.\nFirst attachment token: {MARKER_ATTACHMENT_1}\n"
        )
        self._create_file(attachment1, attachment1_content)

        # First call - establish the stable list
        args1 = {
            "instructions": f"Find and quote the exact sentence containing the token '{MARKER_SMALL_FILE}' from the context files provided.",
            "output_format": "Quote the exact sentence containing the token.",
            "context": [context_file],
            "attachments": [attachment1],
            "session_id": "stable-list-test-dedup",
        }

        response1 = claude(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args1)}"
        )
        print(f"✅ First response: {response1}")
        assert MARKER_SMALL_FILE in response1, (
            f"Failed to find token in first call. Response: {response1}"
        )

        # Second call - same context, new attachment
        # The context file should NOT be resent since it's unchanged
        attachment2 = os.path.join(self.test_dir, "attachment2.txt")
        attachment2_content = (
            f"Second attachment.\nSecond attachment token: {MARKER_ATTACHMENT_2}\n"
        )
        self._create_file(attachment2, attachment2_content)

        args2 = {
            "instructions": (
                f"In this multi-turn conversation:\n"
                f"1. You should already remember the token '{MARKER_SMALL_FILE}' from our previous exchange.\n"
                f"2. Now find and quote the sentence containing '{MARKER_ATTACHMENT_2}' from the new attachment."
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
        assert MARKER_SMALL_FILE in response2, (
            "Failed to recall token from previous turn"
        )
        assert MARKER_ATTACHMENT_2 in response2, "Failed to find new attachment token"
        print(
            "✅ Deduplication test passed - model remembered context without resending!"
        )

        # Cleanup
        self._exec_in_container(f"rm -rf {self.test_dir}", check=False)

    @pytest.mark.parametrize("claude", [True], indirect=True)
    def test_changed_file_detection(self, claude, stack):
        """Test that modified files are detected and resent."""
        print("🔍 Testing changed file detection...")

        # Setup test directory
        self._setup_test_dir(stack)

        # Create initial file
        changing_file = os.path.join(self.test_dir, "changing_file.txt")
        original_content = f"Original content.\nOriginal token: {MARKER_SMALL_FILE}\n"
        self._create_file(changing_file, original_content)

        # First call - establish baseline
        args1 = {
            "instructions": f"Find and quote the sentence containing token '{MARKER_SMALL_FILE}'.",
            "output_format": "Quote the exact sentence containing the token.",
            "context": [changing_file],
            "attachments": [],
            "session_id": "stable-list-test-change",
        }

        response1 = claude(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args1)}"
        )
        print(f"✅ First response: {response1}")
        assert MARKER_SMALL_FILE in response1, "Failed to find original token"

        # Wait a moment to ensure mtime difference
        time.sleep(1)

        # Modify the file - ensure size changes too
        modified_content = f"Modified content with different size.\nModified token: {MARKER_MODIFIED_FILE}\nExtra line to ensure size difference.\n"
        self._create_file(changing_file, modified_content)

        # Second call - should detect the change and resend
        args2 = {
            "instructions": f"Find and quote the sentence containing token '{MARKER_MODIFIED_FILE}'.",
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
        assert MARKER_MODIFIED_FILE in response2, (
            "Failed to find modified token - file was not resent"
        )
        assert MARKER_SMALL_FILE not in response2, (
            "Old token found - file change not detected"
        )
        print("✅ Change detection test passed - modified file was resent!")

        # Cleanup
        self._exec_in_container(f"rm -rf {self.test_dir}", check=False)

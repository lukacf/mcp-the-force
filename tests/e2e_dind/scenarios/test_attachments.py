"""Context overflow test - Verify files are split between inline context and vector store."""

import os
import json
import sys
import pytest

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Unique tokens for different files to verify access from both inline and vector store
INLINE_TOKEN = "mcp-e2e-inline-xyzzy-772"
OVERFLOW_TOKEN = "mcp-e2e-overflow-plugh-772"


@pytest.mark.parametrize("claude", [True, False], indirect=True)
def test_attachment_search_workflow(claude, stack):
    """Test RAG workflow using attachments parameter for automatic vector store creation."""
    print("🔍 Starting robust attachment test...")

    def _exec_in_container(cmd, check=True):
        """Execute a command inside the test-runner container."""
        stdout, stderr, return_code = stack.exec_in_container(
            ["bash", "-c", cmd], "test-runner"
        )
        if check and return_code != 0:
            raise RuntimeError(f"Command failed: {cmd}\nStderr: {stderr}")
        return stdout, stderr, return_code

    def _create_file(path, content):
        """Create a file inside the container with the given content."""
        # Running as root in test-runner, create world-readable files
        import os

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        # Make world-readable so claude user in sub-containers can read
        os.chmod(path, 0o644)

    # Create unique test directory with UUID for per-test isolation
    import os
    import uuid

    test_uuid = uuid.uuid4().hex[:8]
    test_dir = f"/tmp/test_attachments_data_{test_uuid}"

    # Create directory directly with Python (running as root in test-runner)
    os.makedirs(test_dir, exist_ok=True)
    os.chmod(test_dir, 0o755)
    print(f"DEBUG: Created test directory {test_dir} inside container")

    doc1, doc2 = None, None  # Ensure they are defined for the finally block

    try:
        # Step 1: Create a document that CONTAINS the unique token.
        doc1 = os.path.join(test_dir, "doc_with_token.txt")
        doc1_content = (
            f"This document contains a highly secret value.\n"
            f"The secret code is: {INLINE_TOKEN}.\n"
            f"Do not share this code with anyone."
        )
        _create_file(doc1, doc1_content)
        print(f"📄 Created test file with token inside container: {doc1}")

        # Step 2: Search for the token where it exists to confirm baseline functionality.
        args1 = {
            "instructions": f"Quote the exact sentence from the attached document that contains the token '{INLINE_TOKEN}'.",
            "output_format": "A single string containing only the quoted sentence.",
            "context": [],
            "attachments": [doc1],
            "session_id": "rag-test-positive-match",
        }
        response1 = claude(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args1)}"
        )
        print(f"✅ First response (positive match): {response1}")
        assert (
            INLINE_TOKEN in response1
        ), "Model failed to find the unique token when it was present."
        # The model should include the token in its response, but may paraphrase
        print("✅ Positive match test passed!")

        # Step 3: Create a different document that DOES NOT contain the unique token.
        doc2 = os.path.join(test_dir, "doc_without_token.txt")
        doc2_content = (
            "This document discusses the history of the Roman Empire. "
            "It has no secret codes or special tokens."
        )
        _create_file(doc2, doc2_content)
        print(f"📄 Created second test file without token inside container: {doc2}")

        # Step 4: Search for the unique token in the document where it does NOT exist.
        # This is the crucial test for the deduplication cache fix.
        args2 = {
            "instructions": f"Search the attached document for the token '{INLINE_TOKEN}'. If it is not found, you must state that it was not found.",
            "output_format": "A single sentence explaining whether the token was found or not.",
            "context": [],
            # CRITICAL: Use the new document as the attachment.
            "attachments": [doc2],
            "session_id": "rag-test-negative-match",
        }
        response2 = claude(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args2)}"
        )
        print(f"✅ Second response (negative match): {response2}")

        # Step 5: Validate the negative result.
        # The model should explicitly state that the token was not found.
        response2_lower = response2.lower()
        # The model correctly states the token was not found
        assert any(
            phrase in response2_lower
            for phrase in [
                "not found",
                "no information",
                "does not contain",
                "no mention",
                "could not find",
                "is not present",
                "no results",
                "was not found",
            ]
        ), f"Response should have clearly stated the token was not found, but it didn't. Response: {response2}"

        print("✅ Deduplication cache test passed!")

    finally:
        # Cleanup test files inside the container
        _exec_in_container(f"rm -rf {test_dir}", check=False)
        print("🧹 Cleaned up test directory inside container")

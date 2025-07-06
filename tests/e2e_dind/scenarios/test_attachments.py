"""Attachment search test - RAG workflow using attachments parameter."""

import os
import json
import sys

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

# A unique, non-technical token guaranteed not to be in the model's training data.
UNIQUE_TOKEN = "mcp-e2e-flibbertigibbet-772-token"


def test_attachment_search_workflow(claude):
    """Test RAG workflow using attachments parameter for automatic vector store creation."""
    print("🔍 Starting robust attachment test...")

    test_dir = "/host-project/tests/e2e_dind/test_attachments_data"
    os.makedirs(test_dir, exist_ok=True)
    doc1, doc2 = None, None  # Ensure they are defined for the finally block

    try:
        # Step 1: Create a document that CONTAINS the unique token.
        doc1 = os.path.join(test_dir, "doc_with_token.txt")
        with open(doc1, "w") as f:
            f.write(
                f"This document contains a highly secret value.\n"
                f"The secret code is: {UNIQUE_TOKEN}.\n"
                f"Do not share this code with anyone."
            )
        print(f"📄 Created test file with token: {doc1}")

        # Step 2: Search for the token where it exists to confirm baseline functionality.
        args1 = {
            "instructions": f"Quote the exact sentence from the attached document that contains the token '{UNIQUE_TOKEN}'.",
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
            UNIQUE_TOKEN in response1
        ), "Model failed to find the unique token when it was present."
        # The model should include the token in its response, but may paraphrase
        print("✅ Positive match test passed!")

        # Step 3: Create a different document that DOES NOT contain the unique token.
        doc2 = os.path.join(test_dir, "doc_without_token.txt")
        with open(doc2, "w") as f:
            f.write(
                "This document discusses the history of the Roman Empire. "
                "It has no secret codes or special tokens."
            )
        print(f"📄 Created second test file without token: {doc2}")

        # Step 4: Search for the unique token in the document where it does NOT exist.
        # This is the crucial test for the deduplication cache fix.
        args2 = {
            "instructions": f"Search the attached document for the token '{UNIQUE_TOKEN}'. If it is not found, you must state that it was not found.",
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
        # Cleanup test files
        try:
            if doc1 and os.path.exists(doc1):
                os.remove(doc1)
            if doc2 and os.path.exists(doc2):
                os.remove(doc2)
            if os.path.exists(test_dir):
                os.rmdir(test_dir)
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")

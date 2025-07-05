"""Attachment search test - RAG workflow using attachments parameter."""

import os
import json
import sys

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))


def test_attachment_search_workflow(claude):
    """Test RAG workflow using attachments parameter for automatic vector store creation."""
    print("🔍 Starting attachment test with project-safe path...")

    # Step 1: Create test documents in project directory (safe from security restrictions)
    test_dir = "/host-project/tests/e2e_dind/test_attachments_data"
    os.makedirs(test_dir, exist_ok=True)

    try:
        print(f"📁 Created test dir: {test_dir}")

        # Create simple test file in project directory
        doc1 = os.path.join(test_dir, "research_paper.txt")
        with open(doc1, "w") as f:
            f.write("""Machine Learning in Climate Science: A Comprehensive Study
    
Abstract: This paper explores the application of machine learning techniques
in predicting climate patterns and analyzing environmental data.

The QALG-9000 quantum algorithm implements a novel approach to factorization
with efficiency rating O(log³ n) and operates on 256-qubit systems.
""")

        print(f"📄 Created test file: {doc1}")
        print(f"📄 File size: {os.path.getsize(doc1)} bytes")

        # Step 2: Single simple test using project-safe path
        args = {
            "instructions": "Search the attached documents for information about machine learning and summarize what you find.",
            "output_format": "Brief summary of machine learning content found",
            "context": [],
            "attachments": [doc1],  # File in project directory
            "session_id": "rag-project-test",
        }

        print(f"🔧 Testing with args: {json.dumps(args, indent=2)}")

        response = claude(f"Use second-brain chat_with_gpt4_1 with {json.dumps(args)}")

        print(f"✅ Response: {response}")

        # Simple validation like the working test
        assert "machine learning" in response.lower()
        assert len(response.strip()) > 50, "Response should contain substantial content"

        print("✅ Attachment test passed with project-safe path!")

        # Step 3: Test deduplication cache is cleared - create different document
        doc2 = os.path.join(test_dir, "different_paper.txt")
        with open(doc2, "w") as f:
            f.write("""Completely Different Topic: History of Ancient Rome

This document is about Roman history and has nothing to do with machine learning.
The Roman Empire lasted from 27 BC to 476 AD.
Julius Caesar was assassinated in 44 BC.
""")

        print(f"📄 Created second test file: {doc2}")

        # Step 4: Search for the ORIGINAL content with new attachment
        # If dedup cache persists, it might return cached results from first search
        args2 = {
            "instructions": "Search the attached documents for information about the QALG-9000 quantum algorithm.",
            "output_format": "Tell me if you found anything about QALG-9000",
            "context": [],
            "attachments": [doc2],  # Different document that doesn't contain QALG-9000
            "session_id": "rag-test-2",
        }

        response2 = claude(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args2)}"
        )
        print(f"✅ Second response: {response2}")

        # The second search should NOT find QALG-9000 (it's not in doc2)
        # Check if the response indicates QALG-9000 was not found
        response2_lower = response2.lower()
        found_qalg = "qalg-9000" in response2_lower
        indicates_not_found = any(
            phrase in response2_lower
            for phrase in [
                "not found",
                "no information",
                "doesn't contain",
                "no mention",
                "couldn't find",
                "not present",
                "no results",
            ]
        )

        # Either it shouldn't mention QALG-9000 at all, or it should clearly indicate it wasn't found
        assert (
            not found_qalg or indicates_not_found
        ), f"Second search found QALG-9000 in a document that doesn't contain it - possible deduplication cache bug! Response: {response2}"

        print("✅ Deduplication test passed - cache properly cleared between searches!")

    finally:
        # Cleanup test files
        try:
            if os.path.exists(doc1):
                os.remove(doc1)
            if "doc2" in locals() and os.path.exists(doc2):
                os.remove(doc2)
            if os.path.exists(test_dir):
                os.rmdir(test_dir)
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")

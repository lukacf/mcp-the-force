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

    finally:
        # Cleanup test files
        try:
            if os.path.exists(doc1):
                os.remove(doc1)
            if os.path.exists(test_dir):
                os.rmdir(test_dir)
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")

"""Minimal attachment test for debugging."""

import tempfile
import os
import sys

# Add scenarios directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))


def test_simple_attachment(claude):
    """Minimal test to debug attachment processing."""
    print("Starting simple attachment test...")

    # Create a simple test file
    with tempfile.TemporaryDirectory() as tmp_dir:
        print(f"Created temp dir: {tmp_dir}")

        # Create a very simple test file
        test_file = os.path.join(tmp_dir, "simple.txt")
        with open(test_file, "w") as f:
            f.write("This is a simple test file with the word TESTWORD in it.")

        print(f"Created test file: {test_file}")

        # Very simple test without structured output
        response = claude(
            f'Use second-brain chat_with_gpt4_1 with {{"instructions": "Look at the files and tell me if you find TESTWORD", "output_format": "simple text", "context": [], "attachments": ["{tmp_dir}"], "session_id": "simple-test"}}'
        )

        print(f"Response: {response}")

        # Just check if we get any response
        assert len(response) > 0
        print("✅ Simple attachment test passed!")

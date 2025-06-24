"""Cross-tool scenario tests."""

import pytest
import json

pytestmark = pytest.mark.e2e


class TestE2EScenarios:
    """More complex scenarios testing tool interactions."""

    @pytest.mark.timeout(300)  # 5 minutes
    def test_vector_store_workflow(self, claude_code):
        """Test creating and using a vector store."""
        # Use specific Python files from the project
        files = [
            "/app/mcp_second_brain/server.py",
            "/app/mcp_second_brain/tools/definitions.py",
            "/app/README.md",
        ]
        files_json = json.dumps(files)

        # Create vector store with specific output format
        output = claude_code(
            f"Use second-brain create_vector_store_tool with files {files_json}. "
            f'If the tool succeeds and returns a vector_store_id, output exactly "SUCCESS: <id>". '
            f'If it fails, output exactly "FAILED: <reason>".'
        )

        # Check for structured response
        assert "SUCCESS:" in output or "FAILED:" in output
        if "FAILED:" in output:
            # If it failed, make sure it's for a valid reason
            assert "no_supported_files" in output.lower() or "error" in output.lower()

    @pytest.mark.timeout(300)  # 5 minutes
    def test_model_comparison(self, claude_code):
        """Test comparing outputs from different models."""
        import os

        # Skip Gemini tests in CI if no Google credentials
        if os.getenv("CI") and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"):
            pytest.skip("Skipping Gemini test in CI without Google credentials")

        # Try with fast model
        output = claude_code(
            'Use second-brain chat_with_gemini25_flash with instructions "What is 2+2?", '
            'output_format "text", and context []. '
            'Extract just the answer from the response and output only "ANSWER: <number>".'
        )

        # Should contain the structured response
        assert "ANSWER: 4" in output

    @pytest.mark.timeout(600)  # 10 minutes for o3
    def test_o3_session(self, claude_code):
        """Test o3 with session continuity."""
        # First query
        claude_code(
            'Use second-brain chat_with_o3 with instructions "Remember the number 42", '
            'output_format "text", context [], and session_id "test-session-1"'
        )

        # Follow-up query
        output2 = claude_code(
            'Use second-brain chat_with_o3 with instructions "What number did I ask you to remember?", '
            'output_format "text", context [], and session_id "test-session-1"'
        )

        # Should remember
        assert "42" in output2

    @pytest.mark.timeout(300)  # 5 minutes
    def test_multi_turn_chat_gpt4(self, claude_code):
        """Test multi-turn conversation with GPT-4.1."""
        import uuid

        session_id = f"test-gpt4-{uuid.uuid4()}"

        # First turn: Establish context
        args1 = {
            "instructions": "I will tell you two facts. Remember them. My favorite programming language is Python and my favorite number is 42. Reply with OK if you understand.",
            "output_format": "text",
            "context": [],
            "session_id": session_id,
        }
        output1 = claude_code(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args1)}"
        )

        print(f"Turn 1 output: {output1}")
        assert any(
            word in output1.lower()
            for word in ["ok", "understand", "acknowledged", "remember"]
        )

        # Second turn: Test recall
        args2 = {
            "instructions": "What is my favorite programming language? Answer in one word only.",
            "output_format": "text",
            "context": [],
            "session_id": session_id,
        }
        output2 = claude_code(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args2)}"
        )

        print(f"Turn 2 output: {output2}")
        # Should remember Python
        assert "python" in output2.lower()

        # Third turn: Test number recall and calculation
        args3 = {
            "instructions": "What is my favorite number multiplied by 2? Just give the number.",
            "output_format": "text",
            "context": [],
            "session_id": session_id,
        }
        output3 = claude_code(
            f"Use second-brain chat_with_gpt4_1 with {json.dumps(args3)}"
        )

        print(f"Turn 3 output: {output3}")
        # Should calculate 42 * 2 = 84
        assert "84" in output3

    @pytest.mark.timeout(300)  # 5 minutes
    def test_large_context_handling(self, claude_code, tmp_path_factory):
        """Test handling of large context that triggers vector store."""
        # Create a large file (over MAX_INLINE_TOKENS threshold)
        test_dir = tmp_path_factory.mktemp("large-context-test")
        large_file = test_dir / "large_document.md"

        # Create content that's over 12000 tokens with a unique identifier
        content = (
            """# Large Document Test

This document contains a unique identifier: ZEBRA-UNICORN-42

## Section 1: Background
"""
            + ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 50)
            + """

## Section 2: Technical Details
The system uses advanced algorithms for processing.
"""
            + (
                "Technical documentation continues with various implementation details. "
                * 100
            )
            + """

## Section 3: Conclusion
This document serves as a test for large context handling.
Remember the unique identifier mentioned at the beginning.
"""
            + ("Additional content to ensure we exceed the token limit. " * 200)
        )

        large_file.write_text(content)

        context_files = [str(large_file)]
        context_json = json.dumps(context_files)

        output = claude_code(
            f'Use second-brain chat_with_gemini25_flash with instructions="What is the unique identifier mentioned in the document? Just give the identifier.", '
            f'output_format="text", context={context_json}'
        )

        # Should find the unique identifier
        assert "ZEBRA-UNICORN-42" in output

    @pytest.mark.timeout(300)  # 5 minutes
    def test_vector_store_with_attachments(self, claude_code, tmp_path_factory):
        """Test using vector store via attachments parameter."""
        # Create test files with substantial content
        test_dir = tmp_path_factory.mktemp("vector-test")

        # Create multiple files with different content
        file1 = test_dir / "document1.md"
        file1.write_text("""
# Technical Documentation

## System Architecture
The system uses a microservices architecture with the following components:
- API Gateway: Handles all incoming requests
- Auth Service: Manages authentication and authorization
- Data Service: Handles all database operations
- Cache Layer: Redis-based caching for performance

## Security Considerations
All API endpoints require JWT authentication. The tokens expire after 1 hour.
Sensitive data is encrypted at rest using AES-256 encryption.

## Performance Metrics
- Average response time: 150ms
- 99th percentile: 500ms
- Maximum concurrent users: 10,000
""")

        file2 = test_dir / "troubleshooting.md"
        file2.write_text("""
# Troubleshooting Guide

## Common Issues

### Authentication Errors
If you see "401 Unauthorized", check:
1. Token expiration (tokens expire after 1 hour)
2. Correct API key in headers
3. User permissions in the system

### Performance Issues
For slow responses:
1. Check Redis cache status
2. Monitor database query times
3. Review API Gateway logs

### Data Inconsistency
If data appears out of sync:
1. Verify cache invalidation is working
2. Check database replication lag
3. Review transaction logs
""")

        file3 = test_dir / "api_reference.py"
        file3.write_text("""
'''API Reference Implementation'''

class APIClient:
    def __init__(self, api_key: str, base_url: str = "https://api.example.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})
    
    def get_user(self, user_id: int):
        '''Fetch user details by ID.'''
        return self.session.get(f"{self.base_url}/users/{user_id}")
    
    def create_order(self, user_id: int, items: list):
        '''Create a new order for a user.'''
        payload = {"user_id": user_id, "items": items}
        return self.session.post(f"{self.base_url}/orders", json=payload)
    
    def get_metrics(self):
        '''Retrieve system performance metrics.'''
        return self.session.get(f"{self.base_url}/metrics")
""")

        # Use attachments parameter (should trigger vector store creation)
        attachments = [str(file1), str(file2), str(file3)]
        attachments_json = json.dumps(attachments)

        output = claude_code(
            f"Use second-brain chat_with_gpt4_1 with instructions "
            f'"What is the token expiration time mentioned in these documents? Just give the time.", '
            f'output_format "text", context [], and attachments {attachments_json}'
        )

        # Should find "1 hour" mentioned in multiple places
        assert "1 hour" in output.lower() or "one hour" in output.lower()

        # Query about something only in one file
        output2 = claude_code(
            f"Use second-brain chat_with_gpt4_1 with instructions "
            f'"What encryption algorithm is used for data at rest? Just name the algorithm.", '
            f'output_format "text", context [], and attachments {attachments_json}'
        )

        # Should find AES (with or without the key size)
        # Models may return just "AES" or "AES-256" depending on their interpretation
        assert "AES" in output2.upper()

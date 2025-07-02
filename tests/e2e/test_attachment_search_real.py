"""E2E tests for attachment search functionality."""

import pytest
import json

pytestmark = pytest.mark.e2e


@pytest.fixture
def test_documents(tmp_path):
    """Create test documents for attachment search tests."""
    doc1 = tmp_path / "research_paper.txt"
    doc1.write_text("""
    Machine Learning in Climate Science: A Comprehensive Study
    
    Abstract: This paper explores the application of machine learning techniques
    in predicting climate patterns and analyzing environmental data.
    
    Introduction: Climate change represents one of the most significant challenges
    of our time. Machine learning algorithms have shown promise in helping
    scientists better understand complex climate systems.
    
    Methods: We employed deep neural networks and ensemble methods to analyze
    temperature data from weather stations across multiple continents.
    """)

    doc2 = tmp_path / "technical_guide.txt"
    doc2.write_text("""
    Python Development Best Practices
    
    Code Quality Guidelines:
    1. Use type hints for better code documentation
    2. Write comprehensive unit tests
    3. Follow PEP 8 style guidelines
    4. Use virtual environments for dependency management
    
    Testing Framework: pytest is recommended for Python testing
    Version Control: Git with conventional commit messages
    """)

    return [str(doc1), str(doc2)]


class TestAttachmentSearch:
    """Test attachment search functionality - essential tests only."""

    def test_attachment_search_with_o3(self, claude_code, test_documents):
        """Test attachment search with o3 model using low reasoning effort."""
        args = {
            "instructions": "Search the attached documents for information about machine learning and summarize what you find.",
            "output_format": "Brief summary of machine learning content found",
            "context": [],
            "attachments": test_documents,
            "session_id": "test-attachment-search-o3",
            "reasoning_effort": "low",
        }

        prompt = f"Use second-brain chat_with_o3 with {json.dumps(args)}"
        response = claude_code(prompt)

        # Verify the response contains relevant information
        assert "machine learning" in response.lower()
        assert len(response.strip()) > 50, "Response should contain substantial content"

    def test_attachment_search_with_gemini(self, claude_code, test_documents):
        """Test attachment search with Gemini 2.5 Pro."""
        args = {
            "instructions": "Search the attached documents for information about Python development best practices and list the key points.",
            "output_format": "List of Python development best practices found in the documents",
            "context": [],
            "attachments": test_documents,
            "session_id": "test-attachment-search-gemini",
        }

        prompt = f"Use second-brain chat_with_gemini25_pro with {json.dumps(args)}"
        response = claude_code(prompt)

        # Verify the response contains relevant information
        response_lower = response.lower()
        assert any(
            keyword in response_lower
            for keyword in ["python", "type hints", "pytest", "pep 8"]
        )
        assert len(response.strip()) > 50, "Response should contain substantial content"

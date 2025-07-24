"""
Unit tests for token counting functionality.
"""

from unittest.mock import patch, Mock
from mcp_the_force.utils.token_counter import count_tokens


class TestTokenCounter:
    """Test token counting functionality."""

    def test_count_simple_text(self):
        """Test counting tokens in simple text."""
        texts = ["Hello world"]
        count = count_tokens(texts)

        # Should be around 2-3 tokens with tiktoken, or ~2 with fallback
        assert 1 <= count <= 5

    def test_count_multiple_texts(self):
        """Test counting tokens across multiple texts."""
        texts = ["Hello", "world", "from", "Python"]
        count = count_tokens(texts)

        # Should sum all tokens
        assert count >= 4  # At least one token per text

    def test_count_empty_list(self):
        """Test counting tokens in empty list."""
        assert count_tokens([]) == 0

    def test_count_empty_strings(self):
        """Test counting tokens with empty strings."""
        assert count_tokens([""]) == 0
        assert count_tokens(["", "", ""]) == 0

    def test_count_code_snippet(self):
        """Test counting tokens in code."""
        code = """def hello_world():
    print("Hello, world!")
    return 42"""

        count = count_tokens([code])

        # Code usually has more tokens
        assert count > 5

    def test_count_with_fallback(self):
        """Test token counting when tiktoken is not available."""
        # Mock tiktoken not being available
        with patch("mcp_the_force.utils.token_counter._enc", None):
            texts = ["Hello world this is a test"]
            count = count_tokens(texts)

            # Fallback uses len(text) // 4
            # "Hello world this is a test" = 26 chars / 4 = 6
            assert count == max(1, 26 // 4)

    def test_count_with_tiktoken(self):
        """Test token counting with tiktoken encoder."""
        # Mock tiktoken encoder
        mock_enc = Mock()
        mock_enc.encode.return_value = [1, 2, 3]  # 3 tokens

        with patch("mcp_the_force.utils.token_counter._enc", mock_enc):
            texts = ["test text"]
            count = count_tokens(texts)

            assert count == 3
            mock_enc.encode.assert_called_once_with("test text")

    def test_large_text_sequence(self):
        """Test counting tokens in large text sequence."""
        # Create 100 texts
        texts = [f"This is text number {i}" for i in range(100)]
        count = count_tokens(texts)

        # Should be significantly more than 100 tokens
        assert count > 100

    def test_unicode_text(self):
        """Test counting tokens with unicode text."""
        texts = ["Hello 世界", "Привет мир", "🌍🌎🌏"]
        count = count_tokens(texts)

        # Unicode might use more tokens
        assert count > 0

    def test_deterministic_counting(self):
        """Test that token counting is deterministic."""
        texts = ["The quick brown fox", "jumps over", "the lazy dog"]

        # Count multiple times
        counts = [count_tokens(texts) for _ in range(5)]

        # All counts should be the same
        assert len(set(counts)) == 1

    def test_mixed_content(self):
        """Test counting tokens with mixed content types."""
        texts = [
            "Plain text",
            "def function(): pass",
            '{"json": "data"}',
            "# Markdown header",
        ]

        count = count_tokens(texts)

        # Should handle all content types
        assert count > len(texts)  # At least one token per text

"""Tests for Vertex file search functionality."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from mcp_second_brain.adapters.vertex_file_search import GeminiFileSearch, create_file_search_declaration


class TestGeminiFileSearch:
    """Test the GeminiFileSearch class."""

    @pytest.mark.asyncio
    async def test_msearch_no_queries(self):
        """Test msearch with no queries returns empty results."""
        file_search = GeminiFileSearch(["vs_test123"])
        result = await file_search.msearch(None)
        assert result == {"results": []}
        
        result = await file_search.msearch([])
        assert result == {"results": []}

    @pytest.mark.asyncio
    async def test_msearch_limits_queries(self):
        """Test msearch limits queries to 5 max."""
        file_search = GeminiFileSearch(["vs_test123"])
        
        # Mock the client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = []
        mock_client.beta.vector_stores.search = Mock(return_value=mock_response)
        
        with patch('mcp_second_brain.adapters.vertex_file_search.get_openai_client', return_value=mock_client):
            queries = ["q1", "q2", "q3", "q4", "q5", "q6", "q7"]
            await file_search.msearch(queries)
            
            # Should only call search 5 times (5 queries × 1 store)
            assert mock_client.beta.vector_stores.search.call_count == 5

    @pytest.mark.asyncio
    async def test_msearch_formats_results(self):
        """Test msearch formats results correctly."""
        file_search = GeminiFileSearch(["vs_test123"])
        
        # Mock search results
        mock_result = Mock()
        mock_result.content = [{"text": "Test content"}]
        mock_result.score = 0.95
        mock_result.file_name = "test.py"
        mock_result.file_id = "file_123"
        mock_result.metadata = {"type": "code"}
        
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = [mock_result]
        mock_client.beta.vector_stores.search = Mock(return_value=mock_response)
        
        with patch('mcp_second_brain.adapters.vertex_file_search.get_openai_client', return_value=mock_client):
            result = await file_search.msearch(["test query"])
            
            assert "results" in result
            assert len(result["results"]) == 1
            
            formatted_result = result["results"][0]
            assert formatted_result["text"] == "Test content"
            assert formatted_result["metadata"]["file_name"] == "test.py"
            assert formatted_result["metadata"]["score"] == 0.95
            assert formatted_result["metadata"]["type"] == "code"
            assert formatted_result["citation"] == "<source>0</source>"

    @pytest.mark.asyncio
    async def test_msearch_deduplicates_results(self):
        """Test msearch deduplicates identical results."""
        file_search = GeminiFileSearch(["vs_test1", "vs_test2"])
        
        # Create identical results from different stores
        mock_result1 = Mock()
        mock_result1.content = "Duplicate content"
        mock_result1.score = 0.9
        mock_result1.file_name = "test.py"
        mock_result1.file_id = None
        mock_result1.metadata = {}
        
        mock_result2 = Mock()
        mock_result2.content = "Duplicate content"  # Same content
        mock_result2.score = 0.8
        mock_result2.file_name = "test.py"
        mock_result2.file_id = None
        mock_result2.metadata = {}
        
        mock_result3 = Mock()
        mock_result3.content = "Different content"
        mock_result3.score = 0.7
        mock_result3.file_name = "other.py"
        mock_result3.file_id = None
        mock_result3.metadata = {}
        
        mock_client = Mock()
        mock_response1 = Mock()
        mock_response1.data = [mock_result1, mock_result3]
        mock_response2 = Mock()
        mock_response2.data = [mock_result2]
        
        # Return different results for different stores
        mock_client.beta.vector_stores.search = Mock(
            side_effect=[mock_response1, mock_response2]
        )
        
        with patch('mcp_second_brain.adapters.vertex_file_search.get_openai_client', return_value=mock_client):
            result = await file_search.msearch(["test"])
            
            # Should have 2 results (duplicate removed)
            assert len(result["results"]) == 2
            assert result["results"][0]["text"] == "Duplicate content"
            assert result["results"][1]["text"] == "Different content"

    def test_create_file_search_declaration(self):
        """Test function declaration creation."""
        decl = create_file_search_declaration()
        
        assert decl["name"] == "file_search_msearch"
        assert "search over files" in decl["description"]
        assert decl["parameters"]["type"] == "object"
        assert "queries" in decl["parameters"]["properties"]
        assert decl["parameters"]["properties"]["queries"]["type"] == "array"
        assert decl["parameters"]["properties"]["queries"]["maxItems"] == 5
        assert decl["parameters"]["required"] == []  # queries is optional
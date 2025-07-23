"""Unit tests for memory search declaration functions."""

from mcp_second_brain.adapters.memory_search_declaration import (
    create_search_history_declaration_openai,
    create_search_history_declaration_gemini,
)


class TestMemorySearchDeclaration:
    """Test the memory search declaration functions."""

    def test_openai_declaration_structure(self):
        """Test that OpenAI declaration has correct structure for Responses API."""
        declaration = create_search_history_declaration_openai()

        # Check top-level keys
        assert "type" in declaration
        assert declaration["type"] == "function"

        # CRITICAL: For Responses API, function details are at the top level, not nested
        assert "name" in declaration
        assert declaration["name"] == "search_project_history"

        assert "description" in declaration
        assert "Search project history" in declaration["description"]

        assert "parameters" in declaration

        # Check parameters structure
        params = declaration["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params
        assert params["required"] == ["query"]

        # Check properties
        properties = params["properties"]
        assert "query" in properties
        assert "max_results" in properties
        assert "store_types" in properties

        # Verify property types
        assert properties["query"]["type"] == "string"
        assert properties["max_results"]["type"] == "integer"
        assert properties["max_results"]["default"] == 40
        assert properties["store_types"]["type"] == "array"
        assert properties["store_types"]["items"]["type"] == "string"

    def test_gemini_declaration_structure(self):
        """Test that Gemini declaration has correct structure."""
        declaration = create_search_history_declaration_gemini()

        # Gemini doesn't need "type" at top level
        assert "type" not in declaration

        # Check required fields
        assert "name" in declaration
        assert declaration["name"] == "search_project_history"

        assert "description" in declaration
        assert "Search project history" in declaration["description"]

        assert "parameters" in declaration

        # Check parameters
        params = declaration["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params
        assert params["required"] == ["query"]

    def test_declarations_consistency(self):
        """Test that both declarations have consistent functionality."""
        openai_decl = create_search_history_declaration_openai()
        gemini_decl = create_search_history_declaration_gemini()

        # Same function name
        assert openai_decl["name"] == gemini_decl["name"]

        # Same parameters (except for structure differences)
        openai_props = openai_decl["parameters"]["properties"]
        gemini_props = gemini_decl["parameters"]["properties"]

        assert set(openai_props.keys()) == set(gemini_props.keys())

        # Same required fields
        assert (
            openai_decl["parameters"]["required"]
            == gemini_decl["parameters"]["required"]
        )

    def test_openai_declaration_validates_as_tool(self):
        """Test that the OpenAI declaration would be accepted as a valid tool."""
        declaration = create_search_history_declaration_openai()

        # The Responses API expects the function details at the top level
        assert declaration.get("type") == "function"
        assert declaration.get("name") is not None
        assert isinstance(declaration.get("name"), str)
        assert len(declaration.get("name")) > 0

        # Ensure it would work in a tools array
        tools = [declaration]
        assert tools[0]["name"] == "search_project_history"

        # Ensure proper structure
        assert "name" in tools[0]
        assert "type" in tools[0]
        assert "parameters" in tools[0]

    def test_openai_declaration_in_context(self):
        """Test how the declaration would be used in the OpenAI adapter."""
        # Simulate how it's used in the adapter
        tools = []
        tools.append(create_search_history_declaration_openai())

        # The Responses API expects flat structure
        assert tools[0]["type"] == "function"
        assert tools[0]["name"] == "search_project_history"
        assert tools[0]["description"] is not None
        assert tools[0]["parameters"] is not None

        # Ensure the structure matches OpenAI Responses API expectations
        # The API wants: tools = [{"type": "function", "name": "...", "parameters": {...}}]
        tool = tools[0]
        assert all(key in tool for key in ["type", "name", "description", "parameters"])

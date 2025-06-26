"""Function declarations for attachment search tool.

These declarations allow OpenAI and Gemini models to use the
search_session_attachments function to search ephemeral vector stores.
"""


def create_attachment_search_declaration_openai():
    """Create OpenAI-compatible function declaration for attachment search."""
    return {
        "type": "function",
        "name": "search_session_attachments",
        "description": "Search temporary files uploaded as attachments for the current task. Use this when you need to find specific information in large files that were provided as attachments.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query or semicolon-separated queries to find in attachments",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 20)",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    }


def create_attachment_search_declaration_gemini():
    """Create Gemini-compatible function declaration for attachment search."""
    return {
        "name": "search_session_attachments",
        "description": "Search temporary files uploaded as attachments for the current task. Use this when you need to find specific information in large files that were provided as attachments.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query or semicolon-separated queries to find in attachments",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 20)",
                },
            },
            "required": ["query"],
        },
    }

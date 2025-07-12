"""Function declaration for search_project_memory tool.

This provides the function declaration that both OpenAI and Gemini
models can use to call our unified memory search.
"""

from typing import Dict, Any


def create_search_memory_declaration_openai() -> Dict[str, Any]:
    """Create the function declaration for OpenAI Responses API."""
    return {
        "type": "function",
        "name": "search_project_memory",
        "description": (
            "Search project memory for past decisions, conversations, and commits. "
            "Use this to find relevant context from previous AI consultations or git history."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query or semicolon-separated queries",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 40)",
                    "default": 40,
                },
                "store_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Types of stores to search: ['conversation', 'commit']",
                    "default": ["conversation", "commit"],
                },
            },
            "required": ["query"],
        },
    }


def create_search_memory_declaration_gemini() -> Dict[str, Any]:
    """Create the function declaration for Gemini native function calling."""
    return {
        "name": "search_project_memory",
        "description": (
            "Search project memory for past decisions, conversations, and commits. "
            "Use this to find relevant context from previous AI consultations or git history."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query or semicolon-separated queries",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 40,
                },
                "store_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Types of stores to search",
                    "default": ["conversation", "commit"],
                },
            },
            "required": ["query"],
        },
    }

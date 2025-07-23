"""Function declaration for search_project_history tool.

This provides the function declaration that both OpenAI and Gemini
models can use to call our unified memory search.
"""

from typing import Dict, Any


def create_search_history_declaration_openai() -> Dict[str, Any]:
    """Create the function declaration for OpenAI Responses API."""
    return {
        "type": "function",
        "name": "search_project_history",
        "description": (
            "Search project history for past decisions, conversations, and commits. "
            "⚠️ IMPORTANT: Returns HISTORICAL data that may be OUTDATED. "
            "Do NOT use to understand current code state. "
            "Best for finding past design decisions and understanding project evolution."
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
                "session_id": {
                    "type": "string",
                    "description": "Session ID for deduplication scope (optional, defaults to 'default')",
                },
            },
            "required": ["query"],
        },
    }


def create_search_history_declaration_gemini() -> Dict[str, Any]:
    """Create the function declaration for Gemini native function calling."""
    return {
        "name": "search_project_history",
        "description": (
            "Search project history for past decisions, conversations, and commits. "
            "⚠️ IMPORTANT: Returns HISTORICAL data that may be OUTDATED. "
            "Do NOT use to understand current code state. "
            "Best for finding past design decisions and understanding project evolution."
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
                "session_id": {
                    "type": "string",
                    "description": "Session ID for deduplication scope (optional, defaults to 'default')",
                },
            },
            "required": ["query"],
        },
    }

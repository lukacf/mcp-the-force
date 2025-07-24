"""Function declarations for task files search tool.

These declarations allow Gemini and Grok models to use the
search_task_files function to search ephemeral vector stores.
"""

from typing import Dict, Any


def create_task_files_search_declaration_openai() -> Dict[str, Any]:
    """Create OpenAI-compatible function declaration for task files search."""
    return {
        "type": "function",
        "name": "search_task_files",
        "description": "Search files that exceeded context limits and are available in vector stores. Use this when you need to find specific information in files that couldn't fit in the prompt.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query or semicolon-separated queries to find in task files",
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


def create_task_files_search_declaration_gemini() -> Dict[str, Any]:
    """Create Gemini-compatible function declaration for task files search."""
    return {
        "name": "search_task_files",
        "description": "Search files that exceeded context limits and are available in vector stores. Use this when you need to find specific information in files that couldn't fit in the prompt.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query or semicolon-separated queries to find in task files",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 20)",
                },
            },
            "required": ["query"],
        },
    }

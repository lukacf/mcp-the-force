#!/usr/bin/env python3
"""
Script to test MCP call to chat_with_gpt4_1
"""

import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_second_brain.tools.executor import ToolExecutor
from mcp_second_brain.tools.definitions import ChatWithGPT4_1


async def main():
    executor = ToolExecutor()

    # Your exact parameters
    params = {
        "instructions": "Create a person object with name 'Alice' and age 30",
        "output_format": "JSON object with name and age (email optional)",
        "context": [],
        "structured_output_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer", "minimum": 0},
                "email": {"type": "string", "format": "email"},
            },
            "required": ["name", "age"],
            "additionalProperties": False,
        },
        "session_id": "optional-fields-test-bca5ea9d",
    }

    try:
        # Execute the tool
        result = await executor.execute_tool(ChatWithGPT4_1, params)

        # Extract the response content
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                response = result.content[0]
                if hasattr(response, "text"):
                    print(response.text)
                else:
                    print(str(response))
            else:
                print(str(result.content))
        else:
            print(str(result))

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

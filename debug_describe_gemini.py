#!/usr/bin/env python3
"""Debug describe_session for gemini session."""

import asyncio
import json
from mcp_the_force.local_services.describe_session import DescribeSessionService


async def debug_describe():
    """Debug the describe_session for summary-schema-design-gemini."""
    service = DescribeSessionService()

    try:
        result = await service.execute(
            session_id="summary-schema-design-gemini",
            summarization_model="chat_with_gemini25_flash",
        )

        print("Raw result:")
        print(result)
        print("\n" + "=" * 60 + "\n")

        # Try to parse as JSON
        try:
            parsed = json.loads(result)
            print("Parsed JSON:")
            print(json.dumps(parsed, indent=2))
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"First 500 chars: {result[:500]}")

    except Exception as e:
        print(f"Error during execution: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_describe())

#!/usr/bin/env python
"""Test to trace the max_inline_tokens error."""

import asyncio


async def test():
    try:
        # Import and get settings
        from mcp_second_brain.config import get_settings

        settings = get_settings()
        print(
            f"Settings attributes: {[attr for attr in dir(settings) if not attr.startswith('_')]}"
        )
        print(f"context_percentage: {settings.context_percentage}")

        # Try the prompt builder
        from mcp_second_brain.utils.prompt_builder import build_prompt

        prompt, attachments = build_prompt("test", "test", [], model="gemini-2.5-pro")
        print("Prompt built successfully")

    except Exception:
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())

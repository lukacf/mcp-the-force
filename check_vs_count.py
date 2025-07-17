#!/usr/bin/env python3
"""Quick check of current vector store count."""

import asyncio
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv


async def check_count():
    load_dotenv()
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        response = await client.vector_stores.list(limit=100)
        count = len(response.data)
        print(f"Current vector stores: {count}/100")

        if count >= 95:
            print("⚠️  WARNING: Approaching vector store limit!")
        elif count >= 99:
            print("🚨 CRITICAL: At vector store limit - creation will hang!")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(check_count())

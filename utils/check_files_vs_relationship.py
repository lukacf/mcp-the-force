#!/usr/bin/env python3
"""Check the relationship between files and vector stores."""

import asyncio
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv


async def check_relationship():
    load_dotenv()
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Get vector stores
    vs_response = await client.vector_stores.list(limit=10)
    print("Checking first 10 vector stores...")
    print("=" * 60)

    for vs in vs_response.data:
        print(f"\nVector Store: {vs.id}")
        print(f"Created: {vs.created_at}")
        print(f"File counts: {vs.file_counts}")

        # Check if it has files
        if vs.file_counts.total > 0:
            # List files in this vector store
            try:
                files = await client.vector_stores.files.list(
                    vector_store_id=vs.id, limit=5
                )
                print(
                    f"Sample files ({len(files.data)} shown of {vs.file_counts.total}):"
                )
                for f in files.data:
                    print(f"  - {f.id}")
            except Exception as e:
                print(f"  Error listing files: {e}")

    # Also check total file count
    print("\n" + "=" * 60)
    files_response = await client.files.list(purpose="assistants", limit=100)
    print(
        f"\nTotal assistant files: {len(files_response.data)}{'+'if files_response.has_more else ''}"
    )


if __name__ == "__main__":
    asyncio.run(check_relationship())

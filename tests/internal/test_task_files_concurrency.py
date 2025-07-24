import asyncio
from unittest.mock import patch

import pytest

from mcp_the_force.tools.search_task_files import SearchTaskFilesAdapter


@pytest.mark.asyncio
async def test_concurrent_task_files_search_isolation(monkeypatch):
    """Ensure task file IDs do not bleed between concurrent searches."""

    async def fake_search(self, query: str, store_id: str, max_results: int):
        await asyncio.sleep(0.01)
        return [{"content": f"{store_id} result", "store_id": store_id, "score": 1.0}]

    with patch.object(SearchTaskFilesAdapter, "_search_single_store", fake_search):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        adapter1 = SearchTaskFilesAdapter()
        adapter2 = SearchTaskFilesAdapter()

        async def run1():
            return await adapter1.generate(
                prompt="", query="alpha", vector_store_ids=["vs_A"], max_results=1
            )

        async def run2():
            return await adapter2.generate(
                prompt="", query="beta", vector_store_ids=["vs_B"], max_results=1
            )

        res1, res2 = await asyncio.gather(run1(), run2())

        assert "vs_A" in res1
        assert "vs_B" in res2
        assert "vs_B" not in res1
        assert "vs_A" not in res2

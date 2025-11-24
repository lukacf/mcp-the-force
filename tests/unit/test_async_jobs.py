import asyncio
import uuid

import pytest

from mcp_the_force.jobs.queue import get_job_queue
from mcp_the_force.jobs.worker import run_job_once
from mcp_the_force.local_services.async_jobs_service import (
    StartJobService,
    PollJobService,
    CancelJobService,
)


@pytest.mark.asyncio
async def test_enqueue_and_complete_echo(monkeypatch):
    # Use a simple built-in tool that is cheap to run: count_project_tokens with empty context
    queue = get_job_queue()
    await queue._execute_async("DELETE FROM jobs", fetch=False)

    # Start job
    job_id = uuid.uuid4().hex
    await queue.enqueue(job_id, "count_project_tokens", {"items": [__file__]})

    # Before running, status should be pending
    job = await queue.get(job_id)
    assert job["status"] == "pending"

    # Run the job once (synchronous execution via worker helper)
    await run_job_once(job_id)

    # After running, status should be completed and result present
    job = await queue.get(job_id)
    assert job["status"] == "completed"
    assert "result" in job


def test_start_and_poll_tool(monkeypatch):
    service = StartJobService()
    asyncio.get_event_loop().run_until_complete(
        get_job_queue()._execute_async("DELETE FROM jobs", fetch=False)
    )
    job_info = asyncio.get_event_loop().run_until_complete(
        service.execute("count_project_tokens", {"items": [__file__]})
    )
    job_id = job_info["job_id"]

    poll_service = PollJobService()
    poll_resp = asyncio.get_event_loop().run_until_complete(
        poll_service.execute(job_id)
    )
    assert poll_resp["status"] in {"pending", "running"}

    asyncio.get_event_loop().run_until_complete(run_job_once(job_id))
    poll_resp = asyncio.get_event_loop().run_until_complete(
        poll_service.execute(job_id)
    )
    assert poll_resp["status"] == "completed"


def test_cancel_job():
    queue = get_job_queue()
    job_id = uuid.uuid4().hex
    asyncio.get_event_loop().run_until_complete(
        queue.enqueue(job_id, "count_project_tokens", {"items": []})
    )
    cancel_service = CancelJobService()
    asyncio.get_event_loop().run_until_complete(cancel_service.execute(job_id))
    job = asyncio.get_event_loop().run_until_complete(queue.get(job_id))
    assert job["status"] == "cancelled"

"""Simple background worker for executing queued jobs."""

import asyncio
import logging

from ..tools.registry import get_tool
from ..tools.executor import executor
from ..tools.integration import scope_manager  # reuse scope manager for isolation
from .queue import get_job_queue

logger = logging.getLogger(__name__)


async def run_job_once(job_id: str) -> None:
    """Execute a single job by id."""
    queue = get_job_queue()
    job = await queue.get(job_id)
    if not job or job["status"] not in {"pending", "running"}:
        return

    max_runtime_s = job.get("max_runtime_s", 3600)  # Default 1 hour if not specified

    if job["status"] == "pending":
        # claim it
        claimed = await queue.claim_next_pending()
        if not claimed or claimed[0] != job_id:
            return
        _, tool_id, payload, claimed_max_runtime = claimed
        max_runtime_s = claimed_max_runtime or max_runtime_s
    else:
        tool_id = job["tool_id"]
        payload = job["payload"]

    meta = get_tool(tool_id)
    if meta is None:
        await queue.fail(job_id, f"Unknown tool_id {tool_id}")
        return

    try:
        # Execute tool via executor with routed args
        # Pass max_runtime_s as timeout override so async jobs aren't limited by tool's default timeout
        async with scope_manager.scope(f"job_{job_id}"):
            result = await executor.execute(meta, timeout=max_runtime_s, **payload)
        await queue.complete(job_id, result)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"[JOB] job {job_id} failed: {exc}")
        await queue.fail(job_id, str(exc))


async def worker_loop(interval: float = 1.0, stop_event: asyncio.Event | None = None):
    """Continuously run pending jobs."""
    queue = get_job_queue()
    while True:
        if stop_event and stop_event.is_set():
            break
        claimed = await queue.claim_next_pending()
        if claimed:
            job_id, _, _, _ = claimed
            await run_job_once(job_id)
            continue
        await asyncio.sleep(interval)

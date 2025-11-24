"""Local services backing async job tools."""

from typing import Any, Dict

from ..jobs.queue import get_job_queue


class StartJobService:
    async def execute(
        self, target_tool: str, args: Dict[str, Any], max_runtime_s: int = 3600
    ) -> Dict[str, Any]:
        queue = get_job_queue()
        import uuid

        job_id = uuid.uuid4().hex
        await queue.enqueue(
            job_id, target_tool, args or {}, max_runtime_s=max_runtime_s
        )
        return {
            "job_id": job_id,
            "status": "pending",
            "poll_after_seconds": 5,
            "note": "Call poll_job with this job_id until status is completed|failed|cancelled. You may continue other work meanwhile.",
        }


class PollJobService:
    async def execute(self, job_id: str) -> Dict[str, Any]:
        queue = get_job_queue()
        job = await queue.get(job_id)
        if not job:
            return {"error": "job_not_found"}
        return job


class CancelJobService:
    async def execute(self, job_id: str) -> Dict[str, Any]:
        queue = get_job_queue()
        await queue.cancel(job_id)
        return {"job_id": job_id, "status": "cancelled_requested"}

"""Tool specs for async job management."""

from typing import Dict, Any

from .base import ToolSpec
from .registry import tool
from .descriptors import Route
from ..local_services.async_jobs_service import (
    StartJobService,
    PollJobService,
    CancelJobService,
)


@tool
class StartJobTool(ToolSpec):
    """Enqueue a long-running job and return a job_id plus poll instructions."""

    model_name = "start_job"
    adapter_class = None
    description = (
        "Start a long-running job for any registered tool. "
        "Returns job_id immediately; call poll_job(job_id) to retrieve status/result."
    )
    timeout = 30
    service_cls = StartJobService

    target_tool: str = Route.prompt(  # type: ignore[assignment]
        description="ID of the tool to run asynchronously."
    )
    args: Dict[str, Any] = Route.prompt(  # type: ignore[assignment]
        default_factory=dict,
        description="Arguments for the target tool (same schema as the tool itself).",
    )
    max_runtime_s: int = Route.prompt(  # type: ignore[assignment]
        default=3600, description="Maximum runtime for the job in seconds."
    )

    # Values are routed to service execute; no run override needed


@tool
class PollJobTool(ToolSpec):
    """Check job status and retrieve result when ready."""

    model_name = "poll_job"
    adapter_class = None
    description = "Poll the status of a previously started job."
    timeout = 30
    service_cls = PollJobService

    job_id: str = Route.prompt(description="Job identifier returned by start_job.")  # type: ignore[assignment]

    # Routed to service


@tool
class CancelJobTool(ToolSpec):
    """Request cancellation of a pending/running job."""

    model_name = "cancel_job"
    adapter_class = None
    description = "Request cancellation of a job. If already completed, no effect."
    timeout = 30
    service_cls = CancelJobService

    job_id: str = Route.prompt(description="Job identifier to cancel.")  # type: ignore[assignment]

    # Routed to service

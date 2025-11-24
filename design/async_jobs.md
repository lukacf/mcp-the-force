# Async jobs in The Force (MCP)

Goal: support tasks that exceed the 60s MCP tool-call cap (e.g., group_think, high-reasoning LLM calls) without breaking existing synchronous tools.

## User/LLM facing contract

- Start: call `start_job` with `{tool_id, args, max_runtime_s?, priority?, idempotency_key?}`.
- Response within 60s: `{job_id, status: "pending"|"running", poll_after_seconds: 5, note: "Call poll_job(job_id) until status is completed|failed|cancelled. You may continue other work meanwhile. Jobs can run in parallel."}`
- Poll: call `poll_job(job_id)` to get `{status, progress?, result?, error?, suggested_poll_s}`.
- Cancel: `cancel_job(job_id)` → `{status}` (no guarantee if already finished).
- No push notifications; caller must poll. Multiple jobs can be started in parallel.

## Storage (SQLite, local-only)

Tables:
- `jobs(job_id TEXT PK, tool_id TEXT, payload JSON, status TEXT, result JSON, progress REAL, progress_msg TEXT, attempt_count INT, max_attempts INT, started_at INT, updated_at INT, expires_at INT, error_text TEXT, worker_host TEXT, max_runtime_s INT)`
- `job_events(job_id, ts, kind, detail_json)` for lightweight audit/log.

Status values: pending, running, completed, failed, cancelled, expired.

## Worker

- Background thread/async task polls pending jobs, marks running, executes the real tool via existing executor/router.
- Respects `max_runtime_s`; stores partials to `job_events` for visibility.
- On completion/failure updates status/result/error; on cancel check status between chunks.
- Concurrency cap (e.g., 1–2) and queue length cap to avoid local starvation.

## Tool surface to add

- `start_job`: enqueue, return job_id + poll instructions.
- `poll_job`: fetch status/result/progress/error; safe to call repeatedly.
- `cancel_job`: request cancellation.

Optional niceties:
- `list_jobs(status?, limit?)` for manual housekeeping.
- `tail_job(job_id, since_ts?)` to surface `job_events`.

## Integration

- No per-tool duplication. Any existing tool can run async by passing its `tool_id` + routed args into `start_job`.
- Capability validation happens at enqueue; payload stores the same args as the sync path.
- Results are redacted before persistence.

## Timeouts & TTLs

- Per-job `max_runtime_s` (default e.g., 3600s).
- Result retention TTL (e.g., 24h); sweeper marks expired → status=expired and prunes old rows/events.

## Client UX guidance (for LLMs)

- For long tasks: `start_job` → do other work → `poll_job` later. Include `poll_after_seconds` hint.
- Polling cadence: start 5–10s, back off to 30–60s for runs >5 min.
- No push available; caller must remember job_id (or record it in session memory).

## Error handling

- On worker crash/restart: reset stale `running` jobs older than grace window back to `pending`.
- Retry policy optional: `max_attempts` with backoff for transient errors; never retry on user cancel.


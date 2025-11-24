"""SQLite-backed job queue for long-running async tasks."""

import json
import logging
import time
from typing import Any, Dict, Optional, Tuple
from pathlib import Path

from ..sqlite_base_cache import BaseSQLiteCache

logger = logging.getLogger(__name__)


class JobQueue(BaseSQLiteCache):
    """Lightweight job queue to enqueue and track async tasks."""

    def __init__(self, db_path: str, ttl_seconds: int = 24 * 3600):
        create_sql = """
        CREATE TABLE IF NOT EXISTS jobs(
            job_id TEXT PRIMARY KEY,
            tool_id TEXT NOT NULL,
            payload TEXT,
            status TEXT NOT NULL,
            result TEXT,
            progress REAL,
            progress_msg TEXT,
            error_text TEXT,
            attempt_count INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 1,
            max_runtime_s INTEGER DEFAULT 3600,
            started_at INTEGER,
            updated_at INTEGER,
            expires_at INTEGER
        )
        """
        super().__init__(
            db_path=db_path,
            ttl=ttl_seconds,
            table_name="jobs",
            create_table_sql=create_sql,
        )

    async def enqueue(
        self,
        job_id: str,
        tool_id: str,
        payload: Dict[str, Any],
        max_runtime_s: int = 3600,
        expires_at: Optional[int] = None,
    ) -> None:
        now = int(time.time())
        exp = expires_at or now + self.ttl
        await self._execute_async(
            """
            INSERT OR REPLACE INTO jobs(job_id, tool_id, payload, status, result,
                                        progress, progress_msg, error_text,
                                        attempt_count, max_attempts, max_runtime_s,
                                        started_at, updated_at, expires_at)
            VALUES(?,?,?,?,NULL,NULL,NULL,NULL,0,1,?,?,?,?)
            """,
            (
                job_id,
                tool_id,
                json.dumps(payload),
                "pending",
                max_runtime_s,
                now,
                now,
                exp,
            ),
            fetch=False,
        )

    async def claim_next_pending(
        self,
    ) -> Optional[Tuple[str, str, Dict[str, Any], int]]:
        """Atomically claim the next pending job for execution."""
        now = int(time.time())
        rows = await self._execute_async(
            "SELECT job_id, tool_id, payload, max_runtime_s FROM jobs WHERE status='pending' ORDER BY started_at LIMIT 1"
        )
        if not rows:
            return None
        job_id, tool_id, payload_json, max_runtime = rows[0]
        # mark running
        await self._execute_async(
            "UPDATE jobs SET status='running', started_at=?, updated_at=? WHERE job_id=?",
            (now, now, job_id),
            fetch=False,
        )
        return job_id, tool_id, json.loads(payload_json), max_runtime

    async def complete(self, job_id: str, result: Any) -> None:
        now = int(time.time())
        await self._execute_async(
            "UPDATE jobs SET status='completed', result=?, updated_at=? WHERE job_id=?",
            (json.dumps(result), now, job_id),
            fetch=False,
        )

    async def fail(self, job_id: str, error_text: str) -> None:
        now = int(time.time())
        await self._execute_async(
            "UPDATE jobs SET status='failed', error_text=?, updated_at=? WHERE job_id=?",
            (error_text, now, job_id),
            fetch=False,
        )

    async def cancel(self, job_id: str) -> None:
        now = int(time.time())
        await self._execute_async(
            "UPDATE jobs SET status='cancelled', updated_at=? WHERE job_id=?",
            (now, job_id),
            fetch=False,
        )

    async def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        rows = await self._execute_async(
            "SELECT job_id, tool_id, payload, status, result, progress, progress_msg, error_text, started_at, updated_at FROM jobs WHERE job_id=?",
            (job_id,),
        )
        if not rows:
            return None
        (
            job_id,
            tool_id,
            payload_json,
            status,
            result_json,
            progress,
            progress_msg,
            error_text,
            started_at,
            updated_at,
        ) = rows[0]
        return {
            "job_id": job_id,
            "tool_id": tool_id,
            "payload": json.loads(payload_json) if payload_json else {},
            "status": status,
            "result": json.loads(result_json) if result_json else None,
            "progress": progress,
            "progress_msg": progress_msg,
            "error": error_text,
            "started_at": started_at,
            "updated_at": updated_at,
        }

    async def cleanup_expired(self) -> int:
        now = int(time.time())
        rows = await self._execute_async(
            "DELETE FROM jobs WHERE expires_at < ?", (now,), fetch=False
        )
        return 0 if rows is None else 0


job_queue: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    global job_queue
    if job_queue is None:
        from ..config import get_settings

        settings = get_settings()
        db_path = getattr(
            settings, "session_db_path", ".mcp-the-force/sessions.sqlite3"
        )
        queue_db = str((Path(db_path).parent / "jobs.sqlite3").absolute())
        job_queue = JobQueue(db_path=queue_db)
    return job_queue

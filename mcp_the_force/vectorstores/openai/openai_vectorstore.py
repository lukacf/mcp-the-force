"""OpenAI vector store implementation."""

import os
import logging
import time
import asyncio
from typing import Dict, List, Sequence, Optional, Any, BinaryIO
from pathlib import Path
import tempfile

from openai import AsyncOpenAI

from ..protocol import VectorStore, VSFile, SearchResult
from ..errors import QuotaExceededError, AuthError, TransientError

logger = logging.getLogger(__name__)

# Number of parallel batches for upload
PARALLEL_BATCHES = 10

# OpenAI supported file extensions
OPENAI_SUPPORTED_EXTENSIONS = {
    ".c",
    ".cpp",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".go",
    ".html",
    ".java",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".md",
    ".pdf",
    ".php",
    ".pkl",
    ".png",
    ".pptx",
    ".py",
    ".rb",
    ".tar",
    ".tex",
    ".ts",
    ".txt",
    ".webp",
    ".xlsx",
    ".xml",
    ".zip",
}


class OpenAIVectorStore:
    """OpenAI vector store implementation."""

    def __init__(self, client: AsyncOpenAI, store_id: str, name: str):
        self.id = store_id
        self.provider = "openai"
        self.name = name
        self._client = client

    def _is_supported_file(self, file: VSFile) -> bool:
        """Check if file extension is supported by OpenAI."""
        path = Path(file.path)
        ext = path.suffix.lower()
        return ext in OPENAI_SUPPORTED_EXTENSIONS

    async def add_files(self, files: Sequence[VSFile]) -> Sequence[str]:
        """Add files to the vector store using parallel batch uploads."""
        # Filter supported files
        supported_files = []

        for file in files:
            if self._is_supported_file(file):
                supported_files.append(file)
            else:
                logger.warning(f"Skipping unsupported file type: {file.path}")

        if not supported_files:
            return []

        start_time = time.time()
        logger.debug(
            f"Starting upload of {len(supported_files)} files to vector store {self.id}"
        )

        # Create temporary files for upload
        file_streams = []
        temp_files = []

        try:
            # Prepare file streams
            for file in supported_files:
                # Create temp file
                suffix = Path(file.path).suffix
                tf = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
                tf.write(file.content)
                tf.close()
                temp_files.append(tf.name)

                # Open for reading
                file_stream = open(tf.name, "rb")
                file_streams.append(file_stream)

            # Decide whether to use parallel or single batch based on file count
            if len(file_streams) <= 20:
                # For small uploads, use single batch
                logger.debug("Using single batch upload")
                file_batch = (
                    await self._client.vector_stores.file_batches.upload_and_poll(
                        vector_store_id=self.id, files=file_streams
                    )
                )
            else:
                # For larger uploads, use parallel batches
                logger.debug(
                    f"Using parallel batch upload ({PARALLEL_BATCHES} batches)"
                )

                # Split files into batches
                batch_size = max(1, len(file_streams) // PARALLEL_BATCHES)
                batches = []
                for i in range(0, len(file_streams), batch_size):
                    batches.append(file_streams[i : i + batch_size])

                # Ensure we don't have more than PARALLEL_BATCHES
                while len(batches) > PARALLEL_BATCHES:
                    batches[-2].extend(batches[-1])
                    batches.pop()

                logger.debug(
                    f"Created {len(batches)} batches with sizes: {[len(b) for b in batches]}"
                )

                # Upload all batches in parallel
                tasks = [
                    self._upload_batch_with_retry(batch, i + 1)
                    for i, batch in enumerate(batches)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Calculate totals and get last successful batch for return
                total_completed = 0
                total_failed = 0
                total_files = 0
                file_batch = None

                for r in results:
                    if isinstance(r, dict) and "completed" in r:
                        total_completed += r["completed"]
                        total_failed += r["failed"]
                        total_files += r["total"]
                        if "batch" in r and r["batch"]:
                            file_batch = r["batch"]
                    elif isinstance(r, Exception):
                        logger.error(f"Batch failed with exception: {r}")
                        total_failed += 1

                if not file_batch:
                    # All batches failed - create a synthetic batch result
                    class FileCounts:
                        def __init__(self):
                            self.completed = total_completed
                            self.failed = total_failed
                            self.total = total_files
                            self.in_progress = 0
                            self.cancelled = 0

                    class SyntheticBatch:
                        def __init__(self):
                            self.status = (
                                "failed" if total_completed == 0 else "completed"
                            )
                            self.file_counts = FileCounts()

                    file_batch = SyntheticBatch()

            # Log results
            logger.info(
                f"Batch upload completed in {time.time() - start_time:.2f}s - "
                f"Status: {file_batch.status}, File counts: {file_batch.file_counts}"
            )

            # Return file IDs - for now, we'll return empty strings for each file
            # as the batch API doesn't give us individual file IDs
            return ["" for _ in supported_files]

        except asyncio.CancelledError:
            logger.warning("Vector store upload cancelled")
            raise
        finally:
            # Always close file streams and clean up temp files
            for stream in file_streams:
                try:
                    stream.close()
                except Exception:
                    pass

            for temp_path in temp_files:
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                except Exception:
                    pass

    async def _upload_single_batch(
        self,
        files: Sequence[BinaryIO],
        batch_id: str,
        timeout: float = 15.0,
    ) -> dict:
        """Upload a single batch of files without retry logic."""
        start = time.time()
        file_names = []
        for file in files:
            try:
                if hasattr(file, "name"):
                    file_names.append(file.name)
                else:
                    file_names.append(str(file))
            except Exception:
                file_names.append("<unknown>")

        logger.info(f"Batch {batch_id}: Uploading {len(files)} files")

        try:
            file_batch = await asyncio.wait_for(
                self._client.vector_stores.file_batches.upload_and_poll(
                    vector_store_id=self.id, files=files
                ),
                timeout=timeout,
            )

            elapsed = time.time() - start
            completed = file_batch.file_counts.completed
            failed = file_batch.file_counts.failed
            total = file_batch.file_counts.total

            if failed > 0:
                logger.warning(
                    f"Batch {batch_id}: Completed with failures in {elapsed:.2f}s - "
                    f"{completed}/{total} succeeded, {failed} failed"
                )
            else:
                logger.info(
                    f"Batch {batch_id}: Completed successfully in {elapsed:.2f}s - "
                    f"{completed} files uploaded"
                )

            return {
                "batch": file_batch,
                "batch_num": batch_id,
                "elapsed": elapsed,
                "completed": completed,
                "failed": failed,
                "total": total,
                "files": files,
                "failed_files": list(files)
                if failed > 0
                else [],  # Can't tell which failed
            }

        except asyncio.TimeoutError:
            logger.error(f"Batch {batch_id}: Timeout after {timeout}s")
            return {
                "batch": None,
                "batch_num": batch_id,
                "elapsed": time.time() - start,
                "completed": 0,
                "failed": len(files),
                "total": len(files),
                "files": files,
                "failed_files": list(files),
                "error": f"Timeout after {timeout}s",
            }

        except Exception as e:
            elapsed = time.time() - start
            error_msg = str(e)
            logger.error(f"Batch {batch_id}: Failed after {elapsed:.2f}s - {error_msg}")

            # Map to our error types for proper handling
            if "storage limit" in error_msg.lower() or "quota" in error_msg.lower():
                raise QuotaExceededError(f"OpenAI quota exceeded: {error_msg}")
            elif (
                "authentication" in error_msg.lower() or "api key" in error_msg.lower()
            ):
                raise AuthError(f"OpenAI authentication failed: {error_msg}")
            elif "rate limit" in error_msg.lower():
                # Extract retry_after if available
                retry_after = None
                if hasattr(e, "response") and hasattr(e.response, "headers"):
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        retry_after = float(retry_after)
                raise TransientError(
                    f"Rate limited: {error_msg}", retry_after=retry_after
                )

            # For other errors, return failure dict
            return {
                "batch": None,
                "batch_num": batch_id,
                "elapsed": elapsed,
                "completed": 0,
                "failed": len(files),
                "total": len(files),
                "files": files,
                "failed_files": list(files),
                "error": str(e),
            }

    async def _upload_batch_with_retry(
        self,
        files: Sequence[BinaryIO],
        batch_num: int,
        max_retries: int = 3,
    ) -> dict:
        """
        Upload batch with exponential backoff and progressive batch splitting.

        On retry, failed batches are split into smaller chunks and uploaded in parallel.
        """
        backoff_base = 2
        current_files = list(files)  # Convert to list for easier manipulation
        total_completed = 0
        start_time = time.time()

        for attempt in range(max_retries):
            if attempt > 0:
                # Exponential backoff: 2s, 4s, 8s...
                wait_time = backoff_base**attempt
                logger.info(
                    f"Batch {batch_num}: Retry attempt {attempt + 1}/{max_retries} after {wait_time}s backoff"
                )
                await asyncio.sleep(wait_time)

                # Reset file pointers for retry
                for file in current_files:
                    try:
                        if hasattr(file, "seek"):
                            file.seek(0)
                    except Exception as e:
                        logger.warning(f"Could not reset file pointer: {e}")

            try:
                # Determine batch splitting strategy
                if attempt == 0 or len(current_files) <= 3:
                    # Initial attempt or small batch: upload as single batch
                    result = await self._upload_single_batch(
                        current_files, str(batch_num)
                    )

                    if result["failed"] == 0:
                        # Full success
                        result["batch_num"] = batch_num
                        return result
                    elif result["completed"] > 0:
                        # Partial success - track completed and retry failed
                        total_completed += result["completed"]
                        # LIMITATION: OpenAI batch API doesn't tell us which files failed
                        # So we retry ALL files in the batch, which may re-upload successful ones
                        # This wastes bandwidth but ensures failed files get retried
                        current_files = result["failed_files"]
                        logger.info(
                            f"Batch {batch_num}: Partial success {result['completed']}/{result['total']}, "
                            f"will retry all {len(current_files)} files in batch"
                        )
                    else:
                        # Total failure - retry all files
                        current_files = result["failed_files"]

                else:
                    # Split failed batch into smaller chunks for parallel retry
                    split_factor = min(attempt + 1, 4)  # Max 4-way split
                    chunk_size = max(1, len(current_files) // split_factor)
                    sub_batches = []
                    for i in range(0, len(current_files), chunk_size):
                        sub_batches.append(current_files[i : i + chunk_size])

                    logger.info(
                        f"Batch {batch_num}: Splitting {len(current_files)} files into "
                        f"{len(sub_batches)} sub-batches of ~{chunk_size} files each"
                    )

                    # Upload sub-batches in parallel
                    sub_results: List[Any] = await asyncio.gather(
                        *[
                            self._upload_single_batch(sub_batch, f"{batch_num}.{i + 1}")
                            for i, sub_batch in enumerate(sub_batches)
                        ],
                        return_exceptions=True,
                    )

                    # Aggregate results
                    batch_completed = 0
                    failed_files = []

                    for i, result in enumerate(sub_results):
                        if isinstance(result, Exception):
                            logger.error(
                                f"Sub-batch {batch_num}.{i + 1} failed with exception: {result}"
                            )
                            failed_files.extend(sub_batches[i])
                        elif isinstance(result, dict):
                            batch_completed += result.get("completed", 0)
                            failed_files.extend(result.get("failed_files", []))

                    total_completed += batch_completed

                    if not failed_files:
                        # All sub-batches succeeded
                        return {
                            "batch_num": batch_num,
                            "elapsed": time.time() - start_time,
                            "completed": total_completed,
                            "failed": 0,
                            "total": len(files),
                            "files": files,
                            "failed_files": [],
                        }
                    else:
                        # Some sub-batches failed, retry with failed files
                        current_files = failed_files
                        logger.warning(
                            f"Batch {batch_num}: {len(failed_files)} files still failing after split"
                        )

            except Exception as e:
                logger.error(f"Batch {batch_num}: Unexpected error in retry logic: {e}")
                # Continue to next retry attempt
                continue

        # Max retries exhausted
        logger.error(
            f"Batch {batch_num}: Failed after {max_retries} attempts. "
            f"Completed: {total_completed}/{len(files)}"
        )

        return {
            "batch_num": batch_num,
            "elapsed": time.time() - start_time,
            "completed": total_completed,
            "failed": len(files) - total_completed,
            "total": len(files),
            "files": files,
            "failed_files": current_files,
            "error": "Max retries exhausted",
        }

    async def delete_files(self, file_ids: Sequence[str]) -> None:
        """Delete files from the vector store."""
        for file_id in file_ids:
            if file_id:  # Skip empty strings
                try:
                    await self._client.vector_stores.files.delete(
                        vector_store_id=self.id, file_id=file_id
                    )
                except Exception as e:
                    logger.error(f"Failed to delete file {file_id}: {e}")

    async def search(
        self, query: str, k: int = 20, filter: Optional[Dict[str, Any]] = None
    ) -> Sequence[SearchResult]:
        """Search the vector store."""
        # Note: OpenAI doesn't support metadata filtering in vector store search
        # We'll search and then filter results if needed

        try:
            response = await self._client.vector_stores.search(
                vector_store_id=self.id,
                query=query,
                max_num_results=k * 2 if filter else k,  # Get more if filtering
            )

            results = []
            for item in response.data:
                # Extract content
                content = ""
                if hasattr(item, "content"):
                    if isinstance(item.content, str):
                        content = item.content
                    elif isinstance(item.content, list) and item.content:
                        # Try to extract text from first content item
                        first_item = item.content[0]
                        if hasattr(first_item, "text"):
                            if hasattr(first_item.text, "value"):
                                content = first_item.text.value
                            else:
                                content = str(first_item.text)

                # Build metadata
                metadata = {}
                if hasattr(item, "metadata") and item.metadata:
                    metadata = dict(item.metadata)

                # Apply filter if provided
                if filter:
                    match = True
                    for key, value in filter.items():
                        if key not in metadata or metadata[key] != value:
                            match = False
                            break

                    if not match:
                        continue

                results.append(
                    SearchResult(
                        file_id=getattr(item, "file_id", ""),
                        content=content,
                        score=getattr(item, "score", 0.0),
                        metadata=metadata,
                    )
                )

                if len(results) >= k:
                    break

            return results

        except Exception as e:
            error_msg = str(e)
            if "rate limit" in error_msg.lower():
                retry_after = None
                if hasattr(e, "response") and hasattr(e.response, "headers"):
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        retry_after = float(retry_after)
                raise TransientError(
                    f"Rate limited: {error_msg}", retry_after=retry_after
                )
            else:
                raise


class OpenAIClient:
    """OpenAI vector store client."""

    def __init__(self, api_key: str):
        self.provider = "openai"
        self._client = AsyncOpenAI(api_key=api_key)
        self._closed = False

    async def create(self, name: str, ttl_seconds: Optional[int] = None) -> VectorStore:
        """Create a new vector store."""
        if self._closed:
            raise RuntimeError("Client is closed")

        try:
            # Create vector store
            response = await self._client.vector_stores.create(name=name)

            return OpenAIVectorStore(
                client=self._client, store_id=response.id, name=name
            )

        except Exception as e:
            # Map errors
            error_msg = str(e)
            if (
                "limit reached" in error_msg.lower()
                or "quota" in error_msg.lower()
                or "storage limit" in error_msg.lower()
            ):
                raise QuotaExceededError(f"Store limit reached: {error_msg}")
            elif (
                "authentication" in error_msg.lower() or "api key" in error_msg.lower()
            ):
                raise AuthError(f"Invalid API key: {error_msg}")
            else:
                raise

    async def get(self, store_id: str) -> VectorStore:
        """Get an existing vector store."""
        if self._closed:
            raise RuntimeError("Client is closed")

        try:
            # Retrieve store to verify it exists
            response = await self._client.vector_stores.retrieve(store_id)

            return OpenAIVectorStore(
                client=self._client, store_id=store_id, name=response.name or ""
            )

        except Exception as e:
            if "not found" in str(e).lower():
                raise KeyError(f"Store not found: {store_id}")
            else:
                raise

    async def delete(self, store_id: str) -> None:
        """Delete a vector store."""
        if self._closed:
            raise RuntimeError("Client is closed")

        try:
            await self._client.vector_stores.delete(store_id)
        except Exception as e:
            logger.error(f"Failed to delete store {store_id}: {e}")

    async def close(self) -> None:
        """Close the client."""
        self._closed = True
        await self._client.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

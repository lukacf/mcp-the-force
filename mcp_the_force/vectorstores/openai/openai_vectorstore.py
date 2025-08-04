"""OpenAI vector store implementation."""

import logging
import time
import asyncio
import gzip
from typing import Dict, List, Sequence, Optional, Any, BinaryIO
from pathlib import Path

from openai import AsyncOpenAI

from ...adapters.openai.client import OpenAIClientFactory
from ..protocol import VectorStore, VSFile, SearchResult
from ..errors import QuotaExceededError, AuthError, TransientError
from ...dedup.hashing import compute_content_hash
from ...dedup.simple_cache import get_cache
from ...config import get_settings

logger = logging.getLogger(__name__)

# Number of parallel batches for upload
PARALLEL_BATCHES = 10

# OpenAI batch size limit for file associations
ASSOCIATION_BATCH_SIZE = 100

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

        if not supported_files:
            return []

        # DEDUPLICATION: Check for cached files and separate new ones
        files_to_upload = []
        cached_file_ids = []
        failed_cached_files = []  # Files that failed cache association, need to be uploaded
        cache = get_cache()

        for file in supported_files:
            try:
                content_hash = compute_content_hash(file.content)
                cached_file_id = cache.get_file_id(content_hash)

                if cached_file_id:
                    logger.debug(
                        f"DEDUP: Found cached file {cached_file_id} for {file.path}"
                    )
                    cached_file_ids.append(cached_file_id)
                else:
                    files_to_upload.append(file)

            except Exception as e:
                logger.warning(f"Deduplication check failed for {file.path}: {e}")
                files_to_upload.append(file)

        logger.info(
            f"DEDUP: Found {len(cached_file_ids)} cached files, need to upload {len(files_to_upload)} new files"
        )

        # Performance tracking
        total_start_time = time.time()
        upload_start_time = None
        association_start_time = None

        # OPTIMIZATION: Batch associate cached files if we have any
        if cached_file_ids:
            association_start_time = time.time()
            logger.debug(
                f"Starting batch association of {len(cached_file_ids)} cached files"
            )
            try:
                if len(cached_file_ids) > 1:
                    # Use batch association for multiple cached files
                    await self._client.vector_stores.file_batches.create_and_poll(
                        vector_store_id=self.id, file_ids=cached_file_ids
                    )
                    association_time = time.time() - association_start_time
                    logger.debug(
                        f"Batch associated {len(cached_file_ids)} cached files with vector store in {association_time:.2f}s"
                    )
                else:
                    # Single cached file - use individual association
                    await self._client.vector_stores.files.create(
                        vector_store_id=self.id, file_id=cached_file_ids[0]
                    )
                    logger.debug(
                        f"Associated single cached file {cached_file_ids[0]} with vector store"
                    )
            except Exception as e:
                logger.warning(f"Failed to associate cached files: {e}")
                # If batch association fails, we need to identify which files to re-upload
                # For safety, we'll try individual association for each cached file
                successfully_associated = []
                for cached_file_id in cached_file_ids:
                    try:
                        await self._client.vector_stores.files.create(
                            vector_store_id=self.id, file_id=cached_file_id
                        )
                        successfully_associated.append(cached_file_id)
                    except Exception as individual_e:
                        logger.warning(
                            f"Failed to associate cached file {cached_file_id}: {individual_e}"
                        )
                        # Find the original file that corresponds to this cached file and re-upload it
                        for file in supported_files:
                            try:
                                content_hash = compute_content_hash(file.content)
                                if cache.get_file_id(content_hash) == cached_file_id:
                                    failed_cached_files.append(file)
                                    break
                            except Exception:
                                pass

                # Update cached_file_ids to only include successfully associated files
                cached_file_ids = successfully_associated
                # Add failed cached files to upload queue
                files_to_upload.extend(failed_cached_files)

                logger.info(
                    f"DEDUP Fallback: {len(successfully_associated)} cached files associated, "
                    f"{len(failed_cached_files)} failed cached files will be re-uploaded"
                )

        if not files_to_upload:
            # All files were cached and successfully associated
            return cached_file_ids

        upload_start_time = time.time()
        logger.debug(
            f"Starting parallel upload of {len(files_to_upload)} new files to vector store {self.id}"
        )

        # PARALLEL UPLOAD OPTIMIZATION: Upload files in parallel while maintaining reliable file ID caching
        uploaded_file_ids = []

        try:
            if files_to_upload:
                # Phase 1: Parallel upload of new files to get reliable file IDs
                upload_tasks = []
                for file in files_to_upload:
                    task = self._upload_and_cache_file(file, cache)
                    upload_tasks.append(task)

                # Execute all uploads concurrently - this is the key performance improvement
                logger.debug(f"Starting parallel upload of {len(upload_tasks)} files")
                upload_results = await asyncio.gather(
                    *upload_tasks, return_exceptions=True
                )

                # Process results and handle any exceptions
                for i, result in enumerate(upload_results):
                    if isinstance(result, Exception):
                        logger.error(
                            f"Failed to upload file {files_to_upload[i].path}: {result}"
                        )
                    elif isinstance(result, str):
                        # Only add string file_ids, skip None results
                        uploaded_file_ids.append(result)

                logger.debug(
                    f"Parallel upload completed: {len(uploaded_file_ids)}/{len(files_to_upload)} files successful"
                )

                # Phase 2: Batch associate newly uploaded files with vector store
                if uploaded_file_ids:
                    batch_assoc_start = time.time()
                    await self._batch_associate_files(
                        uploaded_file_ids, "newly uploaded"
                    )
                    batch_assoc_time = time.time() - batch_assoc_start
                    logger.debug(
                        f"Batch association of {len(uploaded_file_ids)} new files took {batch_assoc_time:.2f}s"
                    )

            upload_time = time.time() - upload_start_time if upload_start_time else 0
            total_time = time.time() - total_start_time

            logger.info(
                f"Successfully processed {len(cached_file_ids + uploaded_file_ids)} files "
                f"({len(cached_file_ids)} cached, {len(uploaded_file_ids)} uploaded) "
                f"in {total_time:.2f}s (upload: {upload_time:.2f}s)"
            )

            # Return combined file IDs (cached + newly uploaded)
            return cached_file_ids + uploaded_file_ids

        except Exception as e:
            logger.error(f"Error uploading files: {e}")
            return cached_file_ids  # Return at least the cached files

    async def _upload_and_cache_file(self, file: VSFile, cache) -> Optional[str]:
        """Upload a single file using in-memory bytes, cache its ID, and return the file ID.

        This method handles the complete lifecycle of a single file upload:
        1. Convert file content to bytes in memory (no temp files)
        2. Upload to OpenAI using (filename, bytes) tuple format
        3. Cache the content_hash -> file_id mapping

        Args:
            file: The VSFile to upload
            cache: The deduplication cache instance

        Returns:
            The OpenAI file_id if successful, None if failed
        """
        try:
            # Convert file content to bytes in memory - no temp files needed
            file_content_bytes = file.content.encode("utf-8")
            file_name = Path(file.path).name

            # Check if compression should be enabled
            settings = get_settings()
            should_compress = (
                settings.openai.enable_upload_compression
                and len(file_content_bytes)
                >= settings.openai.compression_threshold_bytes
            )

            if should_compress:
                # Compress the content with gzip
                compressed_content = gzip.compress(file_content_bytes)
                compression_ratio = len(compressed_content) / len(file_content_bytes)

                logger.debug(
                    f"Compressing {file_name}: {len(file_content_bytes)} -> {len(compressed_content)} bytes "
                    f"({compression_ratio:.2%} of original size)"
                )

                # Use .gz extension to indicate compression
                file_tuple = (f"{file_name}.gz", compressed_content)
            else:
                # No compression - use original content
                file_tuple = (file_name, file_content_bytes)

            # Upload file to get reliable file_id
            upload_response = await self._client.files.create(
                file=file_tuple, purpose="assistants"
            )
            file_id: str = upload_response.id

            # Cache the file mapping immediately with reliable file_id
            try:
                content_hash = compute_content_hash(file.content)
                cache.cache_file(content_hash, file_id)
                logger.debug(
                    f"DEDUP: Cached uploaded file {file_id} for content hash {content_hash[:12]}..."
                )
            except Exception as e:
                logger.warning(f"Failed to cache uploaded file {file_id}: {e}")

            return file_id

        except Exception as e:
            logger.error(f"Failed to upload file {file.path}: {e}")
            return None

    async def _batch_associate_files(
        self, file_ids: List[str], description: str
    ) -> None:
        """Associate multiple files with the vector store using concurrent, chunked batches.

        Handles the 100-file batch limit by splitting large file lists into smaller chunks
        and processing them concurrently with retry logic and rate limit protection.

        Args:
            file_ids: List of OpenAI file IDs to associate
            description: Description for logging (e.g., "cached" or "newly uploaded")
        """
        if not file_ids:
            return

        # Handle single file case efficiently
        if len(file_ids) == 1:
            try:
                await self._client.vector_stores.files.create(
                    vector_store_id=self.id, file_id=file_ids[0]
                )
                logger.debug(
                    f"Associated single {description} file {file_ids[0]} with vector store"
                )
                return
            except Exception as e:
                logger.error(
                    f"Failed to associate single {description} file {file_ids[0]}: {e}"
                )
                return

        # Split file_ids into chunks respecting the 100-file batch limit
        batches = [
            file_ids[i : i + ASSOCIATION_BATCH_SIZE]
            for i in range(0, len(file_ids), ASSOCIATION_BATCH_SIZE)
        ]

        logger.debug(
            f"Associating {len(file_ids)} {description} files in {len(batches)} concurrent batches"
        )

        # Use semaphore to limit concurrent requests and avoid rate limits
        concurrency_limit = 5  # Conservative limit to avoid rate limiting
        semaphore = asyncio.Semaphore(concurrency_limit)

        async def _associate_batch_with_retry(batch: List[str], batch_num: int) -> bool:
            """Associate a single batch with exponential backoff retry logic."""
            async with semaphore:
                for attempt in range(1, 4):  # Up to 3 attempts
                    try:
                        await self._client.vector_stores.file_batches.create_and_poll(
                            vector_store_id=self.id, file_ids=batch
                        )
                        logger.debug(
                            f"Successfully associated batch {batch_num} ({len(batch)} files)"
                        )
                        return True
                    except Exception as e:
                        if attempt < 3:
                            backoff_time = attempt * 2  # 2s, 4s exponential backoff
                            logger.warning(
                                f"Batch {batch_num} association failed (attempt {attempt}/3): {e}. "
                                f"Retrying in {backoff_time}s..."
                            )
                            await asyncio.sleep(backoff_time)
                        else:
                            logger.error(
                                f"Batch {batch_num} association failed after 3 attempts: {e}"
                            )
                            return False
                return False

        # Execute all batch associations concurrently
        tasks = [
            _associate_batch_with_retry(batch, i + 1) for i, batch in enumerate(batches)
        ]
        results = await asyncio.gather(*tasks)

        # Report results
        successful_batches = sum(1 for result in results if result)
        failed_batches = len(batches) - successful_batches

        if failed_batches == 0:
            logger.info(
                f"Successfully associated all {len(file_ids)} {description} files"
            )
        else:
            logger.warning(
                f"Batch association partially failed: {successful_batches}/{len(batches)} batches succeeded. "
                f"Some {description} files may not be associated with the vector store."
            )

    async def _upload_single_batch(
        self,
        files: Sequence[BinaryIO],
        batch_id: str,
        timeout: float = 60.0,
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
    """OpenAI vector store client that uses the robust client factory."""

    def __init__(self, api_key: str):
        self.provider = "openai"
        self._api_key = api_key
        self._client: Optional[AsyncOpenAI] = None
        self._closed = False

    async def _get_client(self) -> AsyncOpenAI:
        """Lazily initializes and returns the robust OpenAI client."""
        if self._client is None:
            self._client = await OpenAIClientFactory.get_instance(self._api_key)
        return self._client

    async def create(self, name: str, ttl_seconds: Optional[int] = None) -> VectorStore:
        """Create a new vector store."""
        if self._closed:
            raise RuntimeError("Client is closed")

        client = await self._get_client()
        try:
            # Create vector store
            response = await client.vector_stores.create(name=name)

            return OpenAIVectorStore(client=client, store_id=response.id, name=name)

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

        client = await self._get_client()
        try:
            # Retrieve store to verify it exists
            response = await client.vector_stores.retrieve(store_id)

            return OpenAIVectorStore(
                client=client, store_id=store_id, name=response.name or ""
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

        client = await self._get_client()
        try:
            await client.vector_stores.delete(store_id)
        except Exception as e:
            logger.error(f"Failed to delete store {store_id}: {e}")

    async def close(self) -> None:
        """Close the client. No-op as factory manages client lifecycle."""
        self._closed = True
        # We no longer call self._client.close() directly.
        # The factory's close_all() method can be used in tests for explicit cleanup.

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

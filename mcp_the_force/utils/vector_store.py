from typing import List, BinaryIO, Sequence, Tuple
from pathlib import Path
from ..config import get_settings
import logging
import time
import asyncio

# Lazy import OpenAIClientFactory to avoid circular dependency
# It will be imported when needed in the functions that use it

logger = logging.getLogger(__name__)

# Number of parallel batches for upload
PARALLEL_BATCHES = 10


async def _upload_single_batch(
    client, vector_store_id: str, files: Sequence[BinaryIO], batch_id: str, timeout: float = 15.0
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
            client.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store_id, files=files
            ),
            timeout=timeout,
        )

        elapsed = time.time() - start
        completed = file_batch.file_counts.completed
        failed = file_batch.file_counts.failed
        total = file_batch.file_counts.total

        if completed == total:
            logger.info(
                f"Batch {batch_id}: Completed in {elapsed:.2f}s - {completed}/{total} succeeded"
            )
        else:
            logger.warning(
                f"Batch {batch_id}: Completed in {elapsed:.2f}s - {completed}/{total} succeeded, {failed} failed"
            )

        # Track which files failed
        # NOTE: OpenAI batch API doesn't tell us which specific files failed in a batch
        # So on partial failure, we have to retry all files in the batch
        # This is a limitation of the API, not our implementation
        failed_files = list(files) if failed > 0 else []

        return {
            "batch_id": batch_id,
            "elapsed": elapsed,
            "completed": completed,
            "failed": failed,
            "total": total,
            "files": files,
            "failed_files": failed_files,
            "batch": file_batch,
        }

    except asyncio.TimeoutError:
        elapsed = time.time() - start
        logger.warning(
            f"Batch {batch_id}: Timed out after {timeout}s. Files: {file_names}"
        )
        return {
            "batch_id": batch_id,
            "elapsed": elapsed,
            "completed": 0,
            "failed": len(files),
            "total": len(files),
            "files": files,
            "failed_files": list(files),
            "error": "Timeout",
        }

    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"Batch {batch_id}: Failed after {elapsed:.2f}s - {e}")
        return {
            "batch_id": batch_id,
            "elapsed": elapsed,
            "completed": 0,
            "failed": len(files),
            "total": len(files),
            "files": files,
            "failed_files": list(files),
            "error": str(e),
        }


async def _upload_batch_with_retry(
    client, vector_store_id: str, files: Sequence[BinaryIO], batch_num: int, max_retries: int = 3
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
            wait_time = backoff_base ** attempt
            logger.info(
                f"Batch {batch_num}: Retry attempt {attempt + 1}/{max_retries} after {wait_time}s backoff"
            )
            await asyncio.sleep(wait_time)
            
            # Reset file pointers for retry
            for file in current_files:
                try:
                    if hasattr(file, 'seek'):
                        file.seek(0)
                except Exception as e:
                    logger.warning(f"Could not reset file pointer: {e}")
        
        try:
            # Determine batch splitting strategy
            if attempt == 0 or len(current_files) <= 3:
                # Initial attempt or small batch: upload as single batch
                result = await _upload_single_batch(
                    client, vector_store_id, current_files, str(batch_num)
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
                    sub_batches.append(current_files[i:i + chunk_size])
                
                logger.info(
                    f"Batch {batch_num}: Splitting {len(current_files)} files into "
                    f"{len(sub_batches)} sub-batches of ~{chunk_size} files each"
                )
                
                # Upload sub-batches in parallel
                sub_results = await asyncio.gather(*[
                    _upload_single_batch(
                        client, vector_store_id, sub_batch, f"{batch_num}.{i+1}"
                    )
                    for i, sub_batch in enumerate(sub_batches)
                ], return_exceptions=True)
                
                # Aggregate results
                batch_completed = 0
                failed_files = []
                
                for i, result in enumerate(sub_results):
                    if isinstance(result, Exception):
                        logger.error(f"Sub-batch {batch_num}.{i+1} failed with exception: {result}")
                        failed_files.extend(sub_batches[i])
                    elif isinstance(result, dict):
                        batch_completed += result["completed"]
                        if result["failed"] > 0:
                            failed_files.extend(result["failed_files"])
                
                total_completed += batch_completed
                
                if len(failed_files) == 0:
                    # All sub-batches succeeded
                    return {
                        "batch_num": batch_num,
                        "elapsed": time.time() - start_time,
                        "completed": total_completed,
                        "failed": 0,
                        "total": len(files),
                        "retry_attempts": attempt + 1,
                    }
                else:
                    current_files = failed_files
                    logger.warning(
                        f"Batch {batch_num}: After sub-batch retry, "
                        f"{len(failed_files)} files still failing"
                    )
                    
        except Exception as e:
            logger.error(f"Batch {batch_num}: Attempt {attempt + 1} failed with error: {e}")
            # On exception, retry all current files
            continue
    
    # After all retries
    total_failed = len(current_files)
    return {
        "batch_num": batch_num,
        "elapsed": time.time() - start_time,
        "completed": total_completed,
        "failed": total_failed,
        "total": len(files),
        "retry_attempts": max_retries,
        "exhausted_retries": True,
    }


async def _upload_batch(
    client, vector_store_id: str, files: Sequence[BinaryIO], batch_num: int
) -> dict:
    """Upload a batch of files to a vector store with retry logic."""
    return await _upload_batch_with_retry(client, vector_store_id, files, batch_num)


# OpenAI supported file extensions for vector stores
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

# Removed global client singleton - use factory instead for proper event loop scoping


# Temporary compatibility function for memory config
# TODO: Refactor memory config to use async properly
def get_client():
    """
    DEPRECATED: This function is only kept for backward compatibility with memory.config.
    New code should use OpenAIClientFactory.get_instance() instead.
    """
    import warnings

    warnings.warn(
        "get_client() is deprecated. Use OpenAIClientFactory.get_instance() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Return a sync client for the legacy memory config
    # This is not ideal but maintains compatibility
    from openai import OpenAI

    return OpenAI(api_key=get_settings().openai_api_key)


def _is_supported_for_vector_store(file_path: str) -> bool:
    """Check if file extension is supported by OpenAI vector stores."""
    ext = Path(file_path).suffix.lower()

    # Handle files without extensions
    if not ext:
        return False

    return ext in OPENAI_SUPPORTED_EXTENSIONS


async def create_vector_store(paths: List[str]) -> str:
    """
    Create an OpenAI vector store with the given file paths.

    Args:
        paths: List of file paths to include in the vector store

    Returns:
        Vector store ID

    Note:
        Only files with OpenAI-supported extensions will be uploaded.
        Unsupported files will be silently skipped.
    """
    if not paths:
        logger.warning("No paths provided to create_vector_store")
        return ""

    start_time = time.time()
    logger.debug(f"create_vector_store called with {len(paths)} paths")
    logger.debug(f"Input paths: {paths}")

    # Filter for supported file extensions
    supported_paths = [p for p in paths if _is_supported_for_vector_store(p)]
    logger.debug(f"Filtered to {len(supported_paths)} supported files")
    if len(supported_paths) < len(paths):
        unsupported = [p for p in paths if p not in supported_paths]
        logger.warning(f"Skipped {len(unsupported)} unsupported files: {unsupported}")

    if not supported_paths:
        # No supported files to upload
        logger.warning(
            f"No supported files found. Provided extensions: {set(Path(p).suffix.lower() for p in paths)}"
        )
        return ""

    try:
        # Create vector store
        # Use factory to get event-loop scoped client instance
        from ..adapters.openai.client import OpenAIClientFactory

        client = await OpenAIClientFactory.get_instance(
            api_key=get_settings().openai_api_key
        )
        vs = await client.vector_stores.create(name="mcp-the-force-vs")
        logger.info(f"Created vector store {vs.id}")

        # Pre-verify all files exist and are readable
        verified_files = []
        for path in supported_paths:
            try:
                # Check if file exists and is readable
                path_obj = Path(path)
                if path_obj.exists() and path_obj.is_file():
                    # Quick size check (skip empty files)
                    if path_obj.stat().st_size > 0:
                        # Test that we can actually read the file
                        with open(path, "rb") as test_file:
                            test_file.read(1)  # Read one byte to verify access
                        verified_files.append(path)
                        logger.debug(f"Verified file: {path}")
                    else:
                        logger.warning(f"Skipping empty file: {path}")
                else:
                    logger.warning(f"File not found or not accessible: {path}")
            except Exception as e:
                logger.warning(f"Skipping inaccessible file {path}: {e}")

        if not verified_files:
            # No files could be verified
            logger.warning("No accessible files to upload")
            await client.vector_stores.delete(vs.id)
            return ""

        # Open verified files for upload
        file_streams = []
        for path in verified_files:
            try:
                file_stream = open(path, "rb")
                file_streams.append(file_stream)
            except Exception as e:
                logger.error(f"Failed to open verified file {path}: {e}")

        if not file_streams:
            # No files could be opened (shouldn't happen after verification)
            logger.warning("No files could be opened for vector store")
            await client.vector_stores.delete(vs.id)
            return ""

        logger.debug(f"Starting batch upload of {len(file_streams)} files")

        try:
            # Decide whether to use parallel or single batch based on file count
            if len(file_streams) <= 20:
                # For small uploads, use single batch
                file_batch = await client.vector_stores.file_batches.upload_and_poll(
                    vector_store_id=vs.id, files=file_streams
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
                    _upload_batch(client, vs.id, batch, i + 1)
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
        except asyncio.CancelledError:
            # Properly clean up on cancellation
            logger.warning("Vector store upload cancelled, cleaning up resources")
            # Delete the partially created vector store
            try:
                await client.vector_stores.delete(vs.id)
                logger.info(f"Deleted partially created vector store {vs.id}")
            except Exception as e:
                logger.error(
                    f"Failed to delete vector store {vs.id} after cancellation: {e}"
                )
            raise
        finally:
            # Always close file streams
            for stream in file_streams:
                try:
                    stream.close()
                except Exception:
                    pass

        # Only log upload details if file_batch was successfully created (not cancelled)
        logger.info(
            f"Batch upload completed in {time.time() - start_time:.2f}s - Status: {file_batch.status}, File counts: {file_batch.file_counts}"
        )

        # Log details about each file
        if hasattr(file_batch, "file_counts"):
            logger.debug(
                f"Upload details - Completed: {file_batch.file_counts.completed}, "
                f"In progress: {file_batch.file_counts.in_progress}, "
                f"Failed: {file_batch.file_counts.failed}, "
                f"Cancelled: {file_batch.file_counts.cancelled}, "
                f"Total: {file_batch.file_counts.total}"
            )

        if file_batch.file_counts.completed == 0:
            # No files were successfully uploaded
            logger.warning(
                f"No files successfully uploaded. Failed: {file_batch.file_counts.failed}, Cancelled: {file_batch.file_counts.cancelled}"
            )
            try:
                await client.vector_stores.delete(vs.id)
            except Exception:
                pass
            return ""

        return str(vs.id)

    except asyncio.CancelledError:
        # Handle cancellation at the outer level
        logger.warning("create_vector_store operation was cancelled")
        # The vector store ID might have been created before cancellation
        # but cleanup already happened in the inner handler
        raise  # CRITICAL: Re-raise the CancelledError to propagate it up the stack
    except Exception as e:
        logger.error(f"Error creating vector store: {e}")
        return ""


async def delete_vector_store(vector_store_id: str) -> None:
    """
    Delete a vector store after use to clean up resources.

    Args:
        vector_store_id: The ID of the vector store to delete
    """
    if not vector_store_id or not vector_store_id.startswith("vs_"):
        return

    try:
        # Use factory to get event-loop scoped client instance
        from ..adapters.openai.client import OpenAIClientFactory

        client = await OpenAIClientFactory.get_instance(
            api_key=get_settings().openai_api_key
        )
        await client.vector_stores.delete(vector_store_id)
        logger.info(f"Deleted vector store {vector_store_id}")
    except Exception as e:
        logger.warning(f"Failed to delete vector store {vector_store_id}: {e}")


async def add_files_to_vector_store(
    vector_store_id: str, file_paths: List[str], existing_file_paths: List[str]
) -> Tuple[List[str], List[str]]:
    """
    Add new files to an existing vector store, skipping duplicates.

    Args:
        vector_store_id: The vector store to add files to
        file_paths: List of file paths to potentially add
        existing_file_paths: List of file paths already in the vector store

    Returns:
        Tuple of (uploaded_file_ids, skipped_file_paths)
    """
    if not file_paths:
        return [], []

    start_time = time.time()

    # Convert existing paths to a set for efficient lookup
    existing_set = set(existing_file_paths)

    # Filter out files that are already in the vector store
    new_files = []
    skipped_files = []

    for path in file_paths:
        if path in existing_set:
            skipped_files.append(path)
            logger.debug(f"Skipping duplicate file: {path}")
        else:
            new_files.append(path)

    if not new_files:
        logger.info(
            f"All {len(file_paths)} files already exist in vector store {vector_store_id}"
        )
        return [], skipped_files

    logger.info(
        f"Adding {len(new_files)} new files to vector store {vector_store_id} "
        f"(skipped {len(skipped_files)} duplicates)"
    )

    # Filter for supported files
    supported_new_files = [f for f in new_files if _is_supported_for_vector_store(f)]
    if len(supported_new_files) < len(new_files):
        unsupported = [f for f in new_files if f not in supported_new_files]
        logger.warning(f"Skipping {len(unsupported)} unsupported files: {unsupported}")
        skipped_files.extend(unsupported)

    logger.debug(
        f"After filtering: {len(supported_new_files)} supported files out of {len(new_files)} new files"
    )
    if not supported_new_files:
        logger.debug("No supported files, returning early")
        return [], skipped_files

    try:
        logger.debug(
            f"Getting OpenAI client for {len(supported_new_files)} files"
        )
        from ..adapters.openai.client import OpenAIClientFactory
        
        client = await OpenAIClientFactory.get_instance(
            api_key=get_settings().openai_api_key
        )
        logger.debug("Got OpenAI client")

        # Verify and open files
        file_streams = []
        verified_paths = []
        for path in supported_new_files:
            try:
                path_obj = Path(path)
                if (
                    path_obj.exists()
                    and path_obj.is_file()
                    and path_obj.stat().st_size > 0
                ):
                    file_stream = open(path, "rb")
                    file_streams.append(file_stream)
                    verified_paths.append(path)
                else:
                    logger.warning(f"Skipping inaccessible file: {path}")
                    skipped_files.append(path)
            except Exception as e:
                logger.warning(f"Failed to open file {path}: {e}")
                skipped_files.append(path)

        if not file_streams:
            logger.debug("No file streams to upload")
            return [], skipped_files

        logger.debug(f"About to batch upload {len(file_streams)} files")
        # Upload files to the existing vector store using batch upload
        try:
            # Decide whether to use parallel or single batch based on file count
            if len(file_streams) <= 20:
                # For small uploads, use single batch with retry logic
                logger.info(
                    f"Starting single batch upload of {len(file_streams)} files to vector store {vector_store_id}"
                )

                result = await _upload_batch(client, vector_store_id, file_streams, 1)

                logger.info(
                    f"Batch upload completed in {result['elapsed']:.2f}s - "
                    f"Completed: {result['completed']}, Failed: {result['failed']}, Total: {result['total']}"
                )

            else:
                # For larger uploads, use parallel batches
                logger.info(
                    f"Starting parallel batch upload ({PARALLEL_BATCHES} batches) for {len(file_streams)} files to vector store {vector_store_id}"
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

                logger.info(
                    f"Created {len(batches)} batches with sizes: {[len(b) for b in batches]}"
                )

                # Upload all batches in parallel
                tasks = [
                    _upload_batch(client, vector_store_id, batch, i + 1)
                    for i, batch in enumerate(batches)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Calculate totals from successful results
                total_completed = sum(
                    r["completed"]
                    for r in results
                    if isinstance(r, dict) and "completed" in r
                )
                total_failed = sum(
                    r["failed"]
                    for r in results
                    if isinstance(r, dict) and "failed" in r
                )
                total_files = sum(
                    r["total"] for r in results if isinstance(r, dict) and "total" in r
                )

                # Count exception results as failures
                exception_count = sum(1 for r in results if isinstance(r, Exception))
                if exception_count > 0:
                    logger.error(f"{exception_count} batches failed with exceptions")

                elapsed = time.time() - start_time
                logger.info(
                    f"Parallel batch upload completed in {elapsed:.2f}s - "
                    f"Total files: completed={total_completed}, failed={total_failed}, total={total_files}"
                )

            # We can't easily get individual file IDs from batch upload, so return empty list
            # The files are in the vector store, which is what matters
            uploaded_file_ids: List[str] = []

        finally:
            # Close all file streams
            for stream in file_streams:
                try:
                    stream.close()
                except Exception:
                    pass

        return uploaded_file_ids, skipped_files

    except Exception as e:
        logger.error(f"Error adding files to vector store: {e}")
        return [], file_paths  # Consider all files as skipped on error

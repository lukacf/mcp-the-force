from typing import List, BinaryIO, Sequence
from pathlib import Path
from ..config import get_settings
from ..adapters.openai.client import OpenAIClientFactory
import logging
import time
import asyncio

logger = logging.getLogger(__name__)

# Number of parallel batches for upload
PARALLEL_BATCHES = 10


async def _upload_batch(
    client, vector_store_id: str, files: Sequence[BinaryIO], batch_num: int
) -> dict:
    """Upload a single batch of files and return results"""
    start = time.time()

    async def _do_upload():
        """Inner function to perform the actual upload"""
        logger.debug(f"Batch {batch_num}: Uploading {len(files)} files")
        batch = await client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store_id, files=files
        )
        return batch

    # Try upload with timeout and retry
    for attempt in range(2):  # Try twice
        try:
            # 15 second timeout per attempt
            batch = await asyncio.wait_for(_do_upload(), timeout=15.0)

            elapsed = time.time() - start
            logger.info(
                f"Batch {batch_num}: Completed in {elapsed:.2f}s - "
                f"{batch.file_counts.completed}/{batch.file_counts.total} succeeded"
            )
            return {
                "batch_num": batch_num,
                "elapsed": elapsed,
                "completed": batch.file_counts.completed,
                "failed": batch.file_counts.failed,
                "total": batch.file_counts.total,
                "batch": batch,
            }

        except asyncio.TimeoutError:
            elapsed = time.time() - start
            # Log the files that are causing timeout
            file_names = []
            for f in files:
                try:
                    file_names.append(f.name)
                except:
                    file_names.append("<unknown>")

            if attempt == 0:
                logger.warning(
                    f"Batch {batch_num}: Timed out after 15s, switching to file-by-file upload. Files: {file_names}"
                )
                # Instead of retrying the batch, try uploading files one by one
                logger.info(
                    f"Batch {batch_num}: Attempting to upload {len(files)} files individually"
                )

                completed = 0
                failed = 0

                for i, file in enumerate(files):
                    try:
                        file_name = (
                            file.name if hasattr(file, "name") else f"<file_{i}>"
                        )
                        logger.info(
                            f"Batch {batch_num}: Uploading file {i+1}/{len(files)}: {file_name}"
                        )

                        # Upload single file with 10 second timeout
                        single_batch = await asyncio.wait_for(
                            client.vector_stores.file_batches.upload_and_poll(
                                vector_store_id=vector_store_id, files=[file]
                            ),
                            timeout=10.0,
                        )

                        if single_batch.file_counts.completed > 0:
                            completed += 1
                            logger.info(
                                f"Batch {batch_num}: File {i+1}/{len(files)} uploaded successfully: {file_name}"
                            )
                        else:
                            failed += 1
                            logger.error(
                                f"Batch {batch_num}: File {i+1}/{len(files)} failed: {file_name}"
                            )

                    except asyncio.TimeoutError:
                        failed += 1
                        file_name = (
                            file.name if hasattr(file, "name") else f"<file_{i}>"
                        )
                        logger.error(
                            f"Batch {batch_num}: File {i+1}/{len(files)} timed out after 10s: {file_name}"
                        )
                    except Exception as e:
                        failed += 1
                        file_name = (
                            file.name if hasattr(file, "name") else f"<file_{i}>"
                        )
                        logger.error(
                            f"Batch {batch_num}: File {i+1}/{len(files)} error: {file_name} - {e}"
                        )

                elapsed_total = time.time() - start
                logger.info(
                    f"Batch {batch_num}: File-by-file upload completed in {elapsed_total:.2f}s - {completed}/{len(files)} succeeded"
                )

                return {
                    "batch_num": batch_num,
                    "elapsed": elapsed_total,
                    "completed": completed,
                    "failed": failed,
                    "total": len(files),
                    "fallback_mode": "file-by-file",
                }
            else:
                # This shouldn't happen anymore since we don't retry
                logger.error(
                    f"Batch {batch_num}: Timed out after {elapsed:.2f}s. Files: {file_names}"
                )
                return {
                    "batch_num": batch_num,
                    "elapsed": elapsed,
                    "completed": 0,
                    "failed": len(files),
                    "total": len(files),
                    "error": "Timeout",
                }

        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"Batch {batch_num}: Failed after {elapsed:.2f}s - {e}")
            return {
                "batch_num": batch_num,
                "elapsed": elapsed,
                "completed": 0,
                "failed": len(files),
                "total": len(files),
                "error": str(e),
            }


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
    logger.info(f"create_vector_store called with {len(paths)} paths")
    logger.info(f"Input paths: {paths}")

    # Filter for supported file extensions
    supported_paths = [p for p in paths if _is_supported_for_vector_store(p)]
    logger.info(f"Filtered to {len(supported_paths)} supported files")
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
        client = await OpenAIClientFactory.get_instance(
            api_key=get_settings().openai_api_key
        )
        vs = await client.vector_stores.create(name="mcp-second-brain-vs")
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
                        logger.info(f"Verified file: {path}")
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

        logger.info(f"Starting batch upload of {len(file_streams)} files")

        try:
            # Decide whether to use parallel or single batch based on file count
            if len(file_streams) <= 20:
                # For small uploads, use single batch
                file_batch = await client.vector_stores.file_batches.upload_and_poll(
                    vector_store_id=vs.id, files=file_streams
                )
            else:
                # For larger uploads, use parallel batches
                logger.info(f"Using parallel batch upload ({PARALLEL_BATCHES} batches)")

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
            logger.info(
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
        client = await OpenAIClientFactory.get_instance(
            api_key=get_settings().openai_api_key
        )
        await client.vector_stores.delete(vector_store_id)
        logger.info(f"Deleted vector store {vector_store_id}")
    except Exception as e:
        logger.warning(f"Failed to delete vector store {vector_store_id}: {e}")

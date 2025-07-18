"""Utilities for managing files in vector stores."""

from typing import List, Tuple, BinaryIO, Sequence
from pathlib import Path
from ..config import get_settings
from ..adapters.openai.client import OpenAIClientFactory
from .vector_store import _is_supported_for_vector_store
import logging
import time
import asyncio

# Import debug logger (optional)
debug_logger = None  # type: ignore

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
                logger.warning(f"Batch {batch_num}: Timed out after 15s, switching to file-by-file upload. Files: {file_names}")
                # Instead of retrying the batch, try uploading files one by one
                logger.info(f"Batch {batch_num}: Attempting to upload {len(files)} files individually")
                
                completed = 0
                failed = 0
                
                for i, file in enumerate(files):
                    try:
                        file_name = file.name if hasattr(file, 'name') else f"<file_{i}>"
                        logger.info(f"Batch {batch_num}: Uploading file {i+1}/{len(files)}: {file_name}")
                        
                        # Upload single file with 10 second timeout
                        single_batch = await asyncio.wait_for(
                            client.vector_stores.file_batches.upload_and_poll(
                                vector_store_id=vector_store_id, 
                                files=[file]
                            ), 
                            timeout=10.0
                        )
                        
                        if single_batch.file_counts.completed > 0:
                            completed += 1
                            logger.info(f"Batch {batch_num}: File {i+1}/{len(files)} uploaded successfully: {file_name}")
                        else:
                            failed += 1
                            logger.error(f"Batch {batch_num}: File {i+1}/{len(files)} failed: {file_name}")
                            
                    except asyncio.TimeoutError:
                        failed += 1
                        file_name = file.name if hasattr(file, 'name') else f"<file_{i}>"
                        logger.error(f"Batch {batch_num}: File {i+1}/{len(files)} timed out after 10s: {file_name}")
                    except Exception as e:
                        failed += 1
                        file_name = file.name if hasattr(file, 'name') else f"<file_{i}>"
                        logger.error(f"Batch {batch_num}: File {i+1}/{len(files)} error: {file_name} - {e}")
                
                elapsed_total = time.time() - start
                logger.info(f"Batch {batch_num}: File-by-file upload completed in {elapsed_total:.2f}s - {completed}/{len(files)} succeeded")
                
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
                logger.error(f"Batch {batch_num}: Timed out after {elapsed:.2f}s. Files: {file_names}")
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

    logger.info(
        f"[DEBUG] After filtering: {len(supported_new_files)} supported files out of {len(new_files)} new files"
    )
    if not supported_new_files:
        logger.info("[DEBUG] No supported files, returning early")
        return [], skipped_files

    try:
        logger.info(
            f"[DEBUG] Getting OpenAI client for {len(supported_new_files)} files"
        )
        client = await OpenAIClientFactory.get_instance(
            api_key=get_settings().openai_api_key
        )
        logger.info("[DEBUG] Got OpenAI client")

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
            logger.info("[DEBUG] No file streams to upload")
            return [], skipped_files

        logger.info(f"[DEBUG] About to batch upload {len(file_streams)} files")
        # Upload files to the existing vector store using batch upload
        try:
            # Decide whether to use parallel or single batch based on file count
            if len(file_streams) <= 20:
                # For small uploads, use single batch
                logger.info(
                    f"Starting single batch upload of {len(file_streams)} files to vector store {vector_store_id}"
                )

                file_batch = await client.vector_stores.file_batches.upload_and_poll(
                    vector_store_id=vector_store_id, files=file_streams
                )

                logger.info(
                    f"Batch upload completed in {time.time() - start_time:.2f}s - Status: {file_batch.status}, "
                    f"File counts: completed={file_batch.file_counts.completed}, "
                    f"failed={file_batch.file_counts.failed}, "
                    f"total={file_batch.file_counts.total}"
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

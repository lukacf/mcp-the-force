"""Utilities for managing files in vector stores with parallel batch uploads."""

from typing import List, Tuple, BinaryIO, Sequence
from pathlib import Path
from ..config import get_settings
from ..adapters.openai.client import OpenAIClientFactory
from .vector_store import _is_supported_for_vector_store
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
    try:
        logger.debug(f"Batch {batch_num}: Uploading {len(files)} files")
        batch = await client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store_id, files=files
        )
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


async def add_files_to_vector_store_parallel(
    vector_store_id: str, file_paths: List[str], existing_file_paths: List[str]
) -> Tuple[List[str], List[str]]:
    """
    Add new files to an existing vector store using parallel batch uploads.

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

    if not supported_new_files:
        logger.info("No supported files to upload")
        return [], skipped_files

    try:
        client = await OpenAIClientFactory.get_instance(
            api_key=get_settings().openai_api_key
        )

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
            logger.info("No file streams to upload")
            return [], skipped_files

        # Decide whether to use parallel or single batch based on file count
        if len(file_streams) <= 20:
            # For small uploads, use single batch
            logger.info(f"Using single batch upload for {len(file_streams)} files")
            try:
                file_batch = await client.vector_stores.file_batches.upload_and_poll(
                    vector_store_id=vector_store_id, files=file_streams
                )

                logger.info(
                    f"Batch upload completed in {time.time() - start_time:.2f}s - "
                    f"Status: {file_batch.status}, "
                    f"File counts: completed={file_batch.file_counts.completed}, "
                    f"failed={file_batch.file_counts.failed}, "
                    f"total={file_batch.file_counts.total}"
                )

                return [], skipped_files

            finally:
                # Close all file streams
                for stream in file_streams:
                    try:
                        stream.close()
                    except Exception:
                        pass
        else:
            # For larger uploads, use parallel batches
            logger.info(
                f"Using parallel batch upload ({PARALLEL_BATCHES} batches) for {len(file_streams)} files"
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

            try:
                # Upload all batches in parallel
                tasks = [
                    _upload_batch(client, vector_store_id, batch, i + 1)
                    for i, batch in enumerate(batches)
                ]
                results = await asyncio.gather(*tasks)

                # Calculate totals
                total_completed = sum(r["completed"] for r in results)
                total_failed = sum(r["failed"] for r in results)
                total_files = sum(r["total"] for r in results)

                elapsed = time.time() - start_time
                logger.info(
                    f"Parallel batch upload completed in {elapsed:.2f}s - "
                    f"Total files: completed={total_completed}, failed={total_failed}, total={total_files}"
                )

                # Log any failed batches
                failed_batches = [r for r in results if "error" in r]
                if failed_batches:
                    for r in failed_batches:
                        logger.error(
                            f"Batch {r['batch_num']} error: {r.get('error', 'Unknown error')}"
                        )

                return [], skipped_files

            finally:
                # Close all file streams
                for stream in file_streams:
                    try:
                        stream.close()
                    except Exception:
                        pass

    except Exception as e:
        logger.error(f"Error adding files to vector store: {e}")
        return [], file_paths  # Consider all files as skipped on error

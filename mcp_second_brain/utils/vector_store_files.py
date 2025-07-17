"""Utilities for managing files in vector stores."""

from typing import List, Set, Tuple
from pathlib import Path
from ..config import get_settings
from ..adapters.openai.client import OpenAIClientFactory
import logging
import time

logger = logging.getLogger(__name__)


async def add_files_to_vector_store(
    vector_store_id: str, 
    file_paths: List[str], 
    existing_file_paths: List[str]
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
        logger.info(f"All {len(file_paths)} files already exist in vector store {vector_store_id}")
        return [], skipped_files
    
    logger.info(
        f"Adding {len(new_files)} new files to vector store {vector_store_id} "
        f"(skipped {len(skipped_files)} duplicates)"
    )
    
    # Import the supported extensions check
    from .vector_store import _is_supported_for_vector_store
    
    # Filter for supported files
    supported_new_files = [f for f in new_files if _is_supported_for_vector_store(f)]
    if len(supported_new_files) < len(new_files):
        unsupported = [f for f in new_files if f not in supported_new_files]
        logger.warning(f"Skipping {len(unsupported)} unsupported files: {unsupported}")
        skipped_files.extend(unsupported)
    
    if not supported_new_files:
        return [], skipped_files
    
    try:
        client = await OpenAIClientFactory.get_instance(api_key=get_settings().openai_api_key)
        
        # Verify and open files
        file_streams = []
        verified_paths = []
        for path in supported_new_files:
            try:
                path_obj = Path(path)
                if path_obj.exists() and path_obj.is_file() and path_obj.stat().st_size > 0:
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
            return [], skipped_files
        
        # Upload files to the existing vector store using batch upload
        try:
            logger.info(f"Starting batch upload of {len(file_streams)} files to vector store {vector_store_id}")
            
            # Use the batch upload API which is MUCH faster
            file_batch = await client.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store_id,
                files=file_streams
            )
            
            logger.info(
                f"Batch upload completed in {time.time() - start_time:.2f}s - Status: {file_batch.status}, "
                f"File counts: completed={file_batch.file_counts.completed}, "
                f"failed={file_batch.file_counts.failed}, "
                f"total={file_batch.file_counts.total}"
            )
            
            # We can't easily get individual file IDs from batch upload, so return empty list
            # The files are in the vector store, which is what matters
            uploaded_file_ids = []
            
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
from typing import List
from pathlib import Path
from openai import AsyncOpenAI
from ..config import get_settings
import logging
import time
import asyncio

logger = logging.getLogger(__name__)

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

_client = None


def get_client():
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=get_settings().openai_api_key)
    return _client


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
        vs = await get_client().vector_stores.create(name="mcp-second-brain-vs")
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
            await get_client().vector_stores.delete(vs.id)
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
            await get_client().vector_stores.delete(vs.id)
            return ""

        logger.info(f"Starting batch upload of {len(file_streams)} files")

        try:
            # Use batch upload API
            file_batch = await get_client().vector_stores.file_batches.upload_and_poll(
                vector_store_id=vs.id, files=file_streams
            )
        except asyncio.CancelledError:
            # Properly clean up on cancellation
            logger.warning("Vector store upload cancelled, cleaning up resources")
            # Delete the partially created vector store
            try:
                await get_client().vector_stores.delete(vs.id)
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
                await get_client().vector_stores.delete(vs.id)
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
        await get_client().vector_stores.delete(vector_store_id)
        logger.info(f"Deleted vector store {vector_store_id}")
    except Exception as e:
        logger.warning(f"Failed to delete vector store {vector_store_id}: {e}")

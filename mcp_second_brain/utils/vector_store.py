from typing import List
from pathlib import Path
from openai import OpenAI
from ..config import get_settings
import logging
import time

logger = logging.getLogger(__name__)

# OpenAI supported file extensions for vector stores
OPENAI_SUPPORTED_EXTENSIONS = {
    '.c', '.cpp', '.css', '.csv', '.doc', '.docx', '.gif', '.go', 
    '.html', '.java', '.jpeg', '.jpg', '.js', '.json', '.md', '.pdf', 
    '.php', '.pkl', '.png', '.pptx', '.py', '.rb', '.tar', '.tex', 
    '.ts', '.txt', '.webp', '.xlsx', '.xml', '.zip'
}

_client = None

def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=get_settings().openai_api_key)
    return _client


def _is_supported_for_vector_store(file_path: str) -> bool:
    """Check if file extension is supported by OpenAI vector stores."""
    ext = Path(file_path).suffix.lower()
    
    # Handle files without extensions
    if not ext:
        return False
    
    return ext in OPENAI_SUPPORTED_EXTENSIONS

def create_vector_store(paths: List[str]) -> str:
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
    
    # Filter for supported file extensions
    supported_paths = [p for p in paths if _is_supported_for_vector_store(p)]
    logger.info(f"Filtered to {len(supported_paths)} supported files")
    
    if not supported_paths:
        # No supported files to upload
        logger.warning(f"No supported files found. Provided extensions: {set(Path(p).suffix.lower() for p in paths)}")
        return ""
    
    try:
        # Create vector store
        vs = get_client().beta.vector_stores.create(name="mcp-second-brain-vs")
        logger.info(f"Created vector store {vs.id}")
        
        # Open all files
        file_streams = []
        for path in supported_paths:
            try:
                file_streams.append(open(path, "rb"))
            except Exception as e:
                logger.warning(f"Failed to open {path}: {e}")
        
        if not file_streams:
            # No files could be opened
            logger.warning("No files could be opened for vector store")
            get_client().beta.vector_stores.delete(vs.id)
            return ""
        
        logger.info(f"Starting batch upload of {len(file_streams)} files")
        
        # Use batch upload API
        file_batch = get_client().beta.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vs.id,
            files=file_streams
        )
        
        # Close all file streams
        for stream in file_streams:
            try:
                stream.close()
            except:
                pass
        
        logger.info(f"Batch upload completed in {time.time() - start_time:.2f}s - Status: {file_batch.status}, File counts: {file_batch.file_counts}")
        
        if file_batch.file_counts.completed == 0:
            # No files were successfully uploaded
            logger.warning(f"No files successfully uploaded. Failed: {file_batch.file_counts.failed}, Cancelled: {file_batch.file_counts.cancelled}")
            try:
                get_client().beta.vector_stores.delete(vs.id)
            except:
                pass
            return ""
        
        return vs.id
        
    except Exception as e:
        logger.error(f"Error creating vector store: {e}")
        return ""
from typing import List
from pathlib import Path
from openai import OpenAI
from ..config import get_settings

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

def _upload(file_path: str) -> str:
    """Upload a file to OpenAI and return the file ID."""
    with open(file_path, "rb") as fp:
        return get_client().files.create(file=fp, purpose="assistants").id

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
        return ""
    
    # Filter for supported file extensions
    supported_paths = [p for p in paths if _is_supported_for_vector_store(p)]
    
    if not supported_paths:
        # No supported files to upload
        return ""
    
    # Create vector store
    vs = get_client().vector_stores.create(name="mcp-second-brain-vs")
    
    # Upload supported files
    uploaded_count = 0
    for file_path in supported_paths:
        try:
            file_id = _upload(file_path)
            get_client().vector_stores.files.create(vector_store_id=vs.id, file_id=file_id)
            uploaded_count += 1
        except Exception as e:
            # Skip files that fail to upload
            continue
    
    if uploaded_count == 0:
        # No files were successfully uploaded, clean up the empty vector store
        try:
            get_client().vector_stores.delete(vs.id)
        except:
            pass
        return ""
    
    return vs.id
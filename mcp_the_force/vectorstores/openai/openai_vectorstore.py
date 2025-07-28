"""OpenAI vector store implementation."""

import os
import logging
from typing import Dict, List, Sequence, Optional, Any
from pathlib import Path
import tempfile

from openai import AsyncOpenAI

from ..protocol import VectorStore, VSFile, SearchResult
from ..errors import QuotaExceededError, AuthError, TransientError

logger = logging.getLogger(__name__)

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
        """Add files to the vector store."""
        # Filter supported files
        supported_files = []

        for file in files:
            if self._is_supported_file(file):
                supported_files.append(file)
            else:
                logger.warning(f"Skipping unsupported file type: {file.path}")

        if not supported_files:
            return []

        # Upload in batches (OpenAI has a limit of 100 files per batch)
        batch_size = 100
        all_file_ids = []

        for batch_start in range(0, len(supported_files), batch_size):
            batch_end = min(batch_start + batch_size, len(supported_files))
            batch = supported_files[batch_start:batch_end]

            # Upload batch
            batch_ids = await self._upload_batch(batch)
            all_file_ids.extend(batch_ids)

        return all_file_ids

    async def _upload_batch(self, files: List[VSFile]) -> List[str]:
        """Upload a batch of files to OpenAI."""
        try:
            # Create temporary files for upload
            temp_files = []
            file_ids = []

            for file in files:
                # Create temp file
                suffix = Path(file.path).suffix
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=suffix, delete=False
                ) as tf:
                    tf.write(file.content)
                    temp_files.append(tf.name)

            # Upload files
            for temp_path, file in zip(temp_files, files):
                try:
                    with open(temp_path, "rb") as f:
                        # Upload file
                        uploaded_file = await self._client.files.create(
                            file=f, purpose="assistants"
                        )

                    # Attach to vector store
                    vector_file = await self._client.vector_stores.files.create(
                        vector_store_id=self.id, file_id=uploaded_file.id
                    )

                    file_ids.append(vector_file.id)

                except Exception as e:
                    logger.error(f"Failed to upload {file.path}: {e}")
                    file_ids.append("")  # Empty string for failed uploads
                finally:
                    # Clean up temp file
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)

            return file_ids

        except Exception as e:
            # Map to our error types
            error_msg = str(e)
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
            else:
                raise

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

"""Text chunking strategies for HNSW vector store."""

from typing import List


def chunk_text_by_paragraph(text: str) -> List[str]:
    """Simple paragraph-based chunking.

    Args:
        text: Text to chunk

    Returns:
        List of non-empty paragraphs
    """
    return [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]

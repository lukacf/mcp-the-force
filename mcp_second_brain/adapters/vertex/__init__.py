"""Vertex AI adapter package."""

from .adapter import VertexAdapter
from .models import model_context_windows

__all__ = ["VertexAdapter", "model_context_windows"]

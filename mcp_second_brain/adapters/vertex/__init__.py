"""Vertex AI adapter package."""

from .adapter import VertexAdapter
from .models import model_capabilities
from . import cancel_aware_flow  # Apply cancellation patch  # noqa: F401

__all__ = ["VertexAdapter", "model_capabilities"]

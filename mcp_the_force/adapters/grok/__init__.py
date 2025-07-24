"""xAI Grok adapter for MCP The-Force."""

from .adapter import GrokAdapter, GROK_CAPABILITIES
from . import cancel_aware_flow  # Apply cancellation patch  # noqa: F401

__all__ = ["GrokAdapter", "GROK_CAPABILITIES"]

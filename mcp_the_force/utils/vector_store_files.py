"""
DEPRECATED: This module is deprecated and will be removed in a future release.
Please use mcp_the_force.utils.vector_store instead.
"""

import warnings

# Re-export from the new location with deprecation warning
from .vector_store import add_files_to_vector_store as _add_files_to_vector_store
from .vector_store import _is_supported_for_vector_store, PARALLEL_BATCHES

warnings.warn(
    "The vector_store_files module is deprecated. "
    "Please import from mcp_the_force.utils.vector_store instead.",
    DeprecationWarning,
    stacklevel=2,
)


# Create wrapper to ensure warning is shown on usage
async def add_files_to_vector_store(*args, **kwargs):
    """Deprecated: Use mcp_the_force.utils.vector_store.add_files_to_vector_store instead."""
    warnings.warn(
        "add_files_to_vector_store has moved to mcp_the_force.utils.vector_store. "
        "This import path will be removed in a future release.",
        DeprecationWarning,
        stacklevel=2,
    )
    return await _add_files_to_vector_store(*args, **kwargs)


__all__ = [
    "add_files_to_vector_store",
    "_is_supported_for_vector_store",
    "PARALLEL_BATCHES",
]

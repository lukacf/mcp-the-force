"""Override resolution system for Ollama models."""

import fnmatch
import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from ...config import ModelOverride, get_settings
from .discovery import calculate_viable_context, estimate_model_memory_gb

logger = logging.getLogger(__name__)


@dataclass
class ResolvedCapabilities:
    """Resolved model capabilities after applying overrides."""

    model_name: str
    max_context_window: int
    description: str
    source: str  # "override", "detected", "memory-limited", "default"
    memory_warning: Optional[str] = None


def resolve_override(
    model_name: str, overrides: List[ModelOverride]
) -> Optional[ModelOverride]:
    """
    Find the best matching override for a model name.

    Precedence order:
    1. Exact match (highest priority)
    2. Glob pattern match (fnmatch)
    3. Regex pattern match (lowest priority)

    Within each category, the first match wins.
    """
    # 1. Check for exact match
    for override in overrides:
        if (
            override.match
            and override.match == model_name
            and "*" not in override.match
        ):
            logger.debug(f"Exact match override for {model_name}: {override.match}")
            return override

    # 2. Check glob patterns
    for override in overrides:
        if override.match and "*" in override.match:
            if fnmatch.fnmatch(model_name, override.match):
                logger.debug(f"Glob match override for {model_name}: {override.match}")
                return override

    # 3. Check regex patterns
    for override in overrides:
        if override.regex:
            try:
                if re.match(override.regex, model_name):
                    logger.debug(
                        f"Regex match override for {model_name}: {override.regex}"
                    )
                    return override
            except re.error as e:
                logger.warning(f"Invalid regex pattern {override.regex}: {e}")

    return None


async def resolve_model_capabilities(
    model_name: str,
    discovered_info: Dict[str, Any],
    overrides: List[ModelOverride],
    memory_aware: bool = True,
    memory_safety_margin: float = 0.8,
) -> ResolvedCapabilities:
    """
    Resolve final model capabilities considering all factors.

    Args:
        model_name: Name of the model (e.g., "llama3:latest")
        discovered_info: Information from Ollama API discovery
        overrides: List of configured overrides
        memory_aware: Whether to apply memory constraints
        memory_safety_margin: Safety margin for memory calculations

    Returns:
        Resolved capabilities with context window and metadata
    """
    # 1. Start with discovered context, fallback to config default
    settings = get_settings()
    detected_ctx = discovered_info.get(
        "context_window", settings.ollama.default_context_window
    )

    # Build description from discovered info
    description = model_name
    family = discovered_info.get("family", "").title()
    param_size = discovered_info.get("parameter_size", "")

    if family or param_size:
        desc_parts = []
        if family:
            desc_parts.append(family)
        if param_size:
            desc_parts.append(param_size)
        description = f"{model_name} ({' '.join(desc_parts)})"

    source = "discovered"
    memory_warning = None

    # 2. Apply configuration override if exists
    override = resolve_override(model_name, overrides)
    if override and override.max_context_window:
        ctx = override.max_context_window
        description = override.description or description
        source = "override"
        logger.info(f"Applied override for {model_name}: {ctx} tokens")
    else:
        ctx = detected_ctx

    # 3. Apply memory constraints if enabled
    if memory_aware:
        # Estimate model memory usage
        param_size = discovered_info.get("parameter_size", "unknown")
        model_memory_gb = estimate_model_memory_gb(model_name, param_size)

        # Calculate viable context based on available memory
        viable_ctx = await calculate_viable_context(
            model_memory_gb, memory_safety_margin
        )

        if ctx > viable_ctx:
            memory_warning = (
                f"Requested context {ctx} exceeds memory-safe limit {viable_ctx}. "
                f"Model uses ~{model_memory_gb:.1f}GB. Reducing to prevent swapping."
            )
            logger.warning(memory_warning)
            ctx = viable_ctx
            source = "memory-limited"

    return ResolvedCapabilities(
        model_name=model_name,
        max_context_window=ctx,
        description=description,
        source=source,
        memory_warning=memory_warning,
    )

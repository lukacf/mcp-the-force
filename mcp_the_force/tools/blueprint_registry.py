"""Central registry for tool blueprints."""

import logging
from typing import List, Set
from .blueprint import ToolBlueprint

logger = logging.getLogger(__name__)

BLUEPRINTS: List[ToolBlueprint] = []
_REGISTERED_MODELS: Set[str] = set()  # Track registered models to prevent duplicates


def register_blueprints(bps: List[ToolBlueprint]) -> None:
    """Register blueprints from adapters with validation.

    Validates:
    - No duplicate model names
    - All required fields are present
    - Parameter class has proper inheritance
    """
    for bp in bps:
        # Validate blueprint
        _validate_blueprint(bp)

        # Check for duplicates
        if bp.model_name in _REGISTERED_MODELS:
            logger.warning(
                f"Model {bp.model_name} already registered, skipping duplicate"
            )
            continue

        BLUEPRINTS.append(bp)
        _REGISTERED_MODELS.add(bp.model_name)
        logger.debug(f"Registered blueprint for {bp.model_name}")


def _validate_blueprint(bp: ToolBlueprint) -> None:
    """Validate a blueprint before registration.

    Raises:
        ValueError: If blueprint is invalid
    """
    # Check required fields
    if not bp.model_name:
        raise ValueError("Blueprint must have model_name")
    if not bp.adapter_key:
        raise ValueError(f"Blueprint for {bp.model_name} must have adapter_key")
    if not bp.param_class:
        raise ValueError(f"Blueprint for {bp.model_name} must have param_class")
    if not bp.description:
        raise ValueError(f"Blueprint for {bp.model_name} must have description")
    if bp.timeout <= 0:
        raise ValueError(f"Blueprint for {bp.model_name} must have positive timeout")
    if bp.context_window <= 0:
        raise ValueError(
            f"Blueprint for {bp.model_name} must have positive context_window"
        )
    if bp.tool_type not in ("chat", "research"):
        raise ValueError(
            f"Blueprint for {bp.model_name} has invalid tool_type: {bp.tool_type}"
        )

    # Check that param_class inherits from BaseToolParams
    from ..adapters.params import BaseToolParams

    if not issubclass(bp.param_class, BaseToolParams):
        raise ValueError(
            f"Blueprint for {bp.model_name}: param_class must inherit from BaseToolParams"
        )

    # Check parameter-capability consistency
    # This checks that parameters with capability requirements are defined properly
    from .descriptors import RouteDescriptor

    for name in dir(bp.param_class):
        if name.startswith("_"):
            continue
        attr = getattr(bp.param_class, name)
        if isinstance(attr, RouteDescriptor) and attr.requires_capability:
            # Just check it's callable
            if not callable(attr.requires_capability):
                raise ValueError(
                    f"Blueprint for {bp.model_name}: parameter '{name}' has invalid "
                    f"requires_capability - must be callable"
                )


def clear_blueprints() -> None:
    """Clear all registered blueprints (useful for testing)."""
    BLUEPRINTS.clear()
    _REGISTERED_MODELS.clear()


def get_blueprints() -> List[ToolBlueprint]:
    """Get all registered blueprints."""
    return BLUEPRINTS.copy()

"""
Model → CLI Resolution Module.

Maps model names (e.g., "gpt-5.2", "claude-sonnet-4-5") to CLI names (e.g., "codex", "claude")
by reading the `cli` attribute from model blueprints in the adapter registry.
"""

from typing import Dict

from mcp_the_force.tools.blueprint_registry import get_blueprints


class ModelNotFoundError(Exception):
    """Raised when a model name is not found in the adapter registry."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        super().__init__(f"Model not found in registry: {model_name}")


class NoCLIAvailableError(Exception):
    """Raised when a model exists but has no CLI mapping (API-only model)."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        super().__init__(f"Model has no CLI available (API-only): {model_name}")


def resolve_model_to_cli(model_name: str) -> str:
    """
    Resolve a model name to its corresponding CLI name.

    Args:
        model_name: The model identifier (e.g., "gpt-5.2", "claude-sonnet-4-5")

    Returns:
        The CLI name (e.g., "codex", "claude", "gemini")

    Raises:
        ModelNotFoundError: If the model is not in the registry
        NoCLIAvailableError: If the model exists but has no CLI mapping
    """
    # Ensure blueprints are registered (triggers lazy loading)
    from mcp_the_force.tools.registry import list_tools

    list_tools()

    blueprints = get_blueprints()

    # Find blueprint by model name
    for bp in blueprints:
        if bp.model_name == model_name:
            if bp.cli is None:
                raise NoCLIAvailableError(model_name)
            return bp.cli

    raise ModelNotFoundError(model_name)


def get_all_cli_models() -> Dict[str, str]:
    """
    Get all models that have CLI mappings.

    Returns:
        Dict mapping model_name -> cli_name for all models with CLI support
    """
    blueprints = get_blueprints()
    return {bp.model_name: bp.cli for bp in blueprints if bp.cli is not None}

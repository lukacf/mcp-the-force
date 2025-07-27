"""Local service for listing available AI models and their capabilities."""

from typing import List, Dict, Any
from ..tools.registry import list_tools


class ListModelsService:
    """Local service for listing all available AI models and their capabilities."""

    async def execute(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """List all available AI models and their capabilities.

        Returns:
            List of model information including names, providers, and capabilities
        """
        models = []
        tools = list_tools()

        for tool_id, metadata in tools.items():
            # Skip aliases
            if (
                metadata.spec_class.__doc__
                and "Alias for" in metadata.spec_class.__doc__
            ):
                continue

            model_info = {
                "id": tool_id,
                "provider": metadata.model_config["adapter_class"],
                "model": metadata.model_config["model_name"],
                "context_window": metadata.model_config["context_window"],
                "timeout": metadata.model_config["timeout"],
                "description": metadata.model_config["description"],
                "parameters": [],
            }

            # Add parameter information
            for param_name, param_info in metadata.parameters.items():
                # Check if parameter has capability requirements
                if param_info.requires_capability and metadata.capabilities:
                    try:
                        # Check if the model supports this parameter
                        if not param_info.requires_capability(metadata.capabilities):
                            # Skip this parameter - not supported by model
                            continue
                    except Exception:
                        # If capability check fails, skip the parameter
                        continue

                model_info["parameters"].append(
                    {
                        "name": param_name,
                        "type": param_info.type_str,
                        "required": param_info.required,
                        "route": param_info.route,
                        "description": param_info.description,
                    }
                )

            models.append(model_info)

        return models
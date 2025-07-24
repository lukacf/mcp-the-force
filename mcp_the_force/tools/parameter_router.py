"""Parameter routing for tools."""

import logging
from typing import Dict, Any, List, Union
from .registry import ToolMetadata
from .descriptors import RouteType

logger = logging.getLogger(__name__)


class ParameterRouter:
    """Routes parameters to their designated handlers."""

    def route(
        self, metadata: ToolMetadata, params: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any] | list]:
        """Route parameters based on their descriptors.

        Args:
            metadata: Tool metadata with parameter routing info
            params: Validated parameters

        Returns:
            Dict with routed parameters:
            - "prompt": Dict of prompt parameters
            - "adapter": Dict of adapter parameters
            - "vector_store": List of file paths
            - "session": Dict of session parameters
            - "vector_store_ids": List of store IDs
        """
        routed: Dict[str, Union[Dict[str, Any], List[Any]]] = {
            "prompt": {},
            "adapter": {},
            "vector_store": [],
            "session": {},
            "vector_store_ids": [],
            "structured_output": {},
        }

        # Sort prompt parameters by position
        prompt_params = []

        for name, value in params.items():
            if value is None:
                continue

            param_info = metadata.parameters[name]
            route = param_info.route

            if route == RouteType.PROMPT:
                if param_info.position is not None:
                    prompt_params.append((param_info.position, name, value))
                else:
                    prompt_dict = routed["prompt"]
                    assert isinstance(prompt_dict, dict)
                    prompt_dict[name] = value
            elif route == RouteType.ADAPTER:
                adapter_dict = routed["adapter"]
                assert isinstance(adapter_dict, dict)
                adapter_dict[name] = value
            elif route == RouteType.VECTOR_STORE:
                # Handle multiple vector_store parameters
                vector_list = routed["vector_store"]
                assert isinstance(vector_list, list)
                if isinstance(value, list):
                    vector_list.extend(value)
                else:
                    vector_list.append(value)
            elif route == RouteType.SESSION:
                session_dict = routed["session"]
                assert isinstance(session_dict, dict)
                session_dict[name] = value
            elif route == RouteType.VECTOR_STORE_IDS:
                vs_ids = routed["vector_store_ids"]
                assert isinstance(vs_ids, list)
                if isinstance(value, list):
                    vs_ids.extend(value)
                else:
                    vs_ids.append(value)
            elif route == RouteType.STRUCTURED_OUTPUT:
                structured_dict = routed["structured_output"]
                assert isinstance(structured_dict, dict)
                structured_dict[name] = value
            else:
                logger.warning(f"Unknown route '{route}' for parameter '{name}'")

        # Add positional prompt parameters in order
        prompt_params.sort(key=lambda x: x[0])
        prompt_dict = routed["prompt"]
        assert isinstance(prompt_dict, dict)
        for _, name, value in prompt_params:
            prompt_dict[name] = value

        return routed

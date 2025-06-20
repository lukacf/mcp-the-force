"""Parameter routing for tools."""
import logging
from typing import Dict, Any
from .registry import ToolMetadata

logger = logging.getLogger(__name__)


class ParameterRouter:
    """Routes parameters to their designated handlers."""
    
    def route(
        self, 
        metadata: ToolMetadata, 
        params: Dict[str, Any]
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
        """
        routed = {
            "prompt": {},
            "adapter": {},
            "vector_store": [],
            "session": {}
        }
        
        # Sort prompt parameters by position
        prompt_params = []
        
        for name, value in params.items():
            if value is None:
                continue
                
            param_info = metadata.parameters[name]
            route = param_info.route
            
            if route == "prompt":
                if param_info.position is not None:
                    prompt_params.append((param_info.position, name, value))
                else:
                    routed["prompt"][name] = value
            elif route == "adapter":
                routed["adapter"][name] = value
            elif route == "vector_store":
                # Handle multiple vector_store parameters
                if isinstance(value, list):
                    routed["vector_store"].extend(value)
                else:
                    routed["vector_store"].append(value)
            elif route == "session":
                routed["session"][name] = value
            else:
                logger.warning(f"Unknown route '{route}' for parameter '{name}'")
        
        # Add positional prompt parameters in order
        prompt_params.sort(key=lambda x: x[0])
        for _, name, value in prompt_params:
            routed["prompt"][name] = value
        
        return routed
"""Executor for dataclass-based tools."""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from ..adapters import get_adapter
from ..utils.prompt_builder import build_prompt
from ..utils.vector_store import create_vector_store, delete_vector_store
from ..session_cache import session_cache
from .registry import ToolMetadata, ParameterInfo
from .base import ToolSpec

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Handles execution of tools based on their metadata."""
    
    async def execute(self, metadata: ToolMetadata, **kwargs) -> str:
        """Execute a tool with the given arguments.
        
        Args:
            metadata: Tool metadata containing routing information
            **kwargs: User-provided arguments
            
        Returns:
            Response from the model as a string
        """
        start_time = asyncio.get_event_loop().time()
        tool_id = metadata.id
        
        try:
            # 1. Create tool instance and validate inputs
            tool_instance = metadata.spec_class()
            validated_params = self._validate_and_set_params(tool_instance, metadata, kwargs)
            
            # 2. Route parameters
            routed_params = self._route_parameters(metadata, validated_params)
            
            # 3. Build prompt
            prompt = await self._build_prompt(routed_params["prompt"])
            
            # 4. Handle vector store if needed
            vs_id = None
            vector_store_ids = None
            if routed_params["vector_store"]:
                vs_id = await self._create_vector_store(routed_params["vector_store"])
                vector_store_ids = [vs_id] if vs_id else None
            
            # 5. Get adapter
            adapter, error = get_adapter(
                metadata.model_config["adapter_class"],
                metadata.model_config["model_name"]
            )
            if not adapter:
                return f"Error: Failed to initialize adapter: {error}"
            
            # 6. Handle session
            previous_response_id = None
            session_id = routed_params["session"].get("session_id")
            if session_id:
                previous_response_id = session_cache.get_response_id(session_id)
                if previous_response_id:
                    logger.info(f"Continuing session {session_id}")
            
            # 7. Execute model call
            adapter_params = routed_params["adapter"]
            if previous_response_id:
                adapter_params["previous_response_id"] = previous_response_id
            
            result = await asyncio.wait_for(
                adapter.generate(
                    prompt=prompt,
                    vector_store_ids=vector_store_ids,
                    timeout=metadata.model_config["timeout"],
                    **adapter_params
                ),
                timeout=metadata.model_config["timeout"]
            )
            
            # 8. Handle response
            if isinstance(result, dict):
                content = result.get("content", "")
                # Store response ID for next call if session provided
                if session_id and "response_id" in result:
                    session_cache.set_response_id(session_id, result["response_id"])
                return content
            else:
                # Vertex adapter returns string directly
                return result
                
        finally:
            # Cleanup
            if vs_id:
                try:
                    delete_vector_store(vs_id)
                except Exception as e:
                    logger.error(f"Error deleting vector store: {e}")
            
            elapsed = asyncio.get_event_loop().time() - start_time
            logger.info(f"{tool_id} completed in {elapsed:.2f}s")
    
    def _validate_and_set_params(
        self, 
        tool_instance: ToolSpec, 
        metadata: ToolMetadata, 
        kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate parameters and set them on the tool instance."""
        validated = {}
        
        # Check required parameters
        for name, param_info in metadata.parameters.items():
            if param_info.required and name not in kwargs:
                raise ValueError(f"Missing required parameter: {name}")
            
            # Get value or use default
            if name in kwargs:
                value = kwargs[name]
            else:
                value = param_info.default
            
            # Check that required parameters are not None
            if param_info.required and value is None:
                raise ValueError(f"Required parameter '{name}' cannot be None")
            
            # Set on instance (descriptor will handle storage)
            setattr(tool_instance, name, value)
            validated[name] = value
        
        # Check for unknown parameters
        known_params = set(metadata.parameters.keys())
        unknown = set(kwargs.keys()) - known_params
        if unknown:
            logger.warning(f"Unknown parameters will be ignored: {unknown}")
        
        return validated
    
    def _route_parameters(
        self, 
        metadata: ToolMetadata, 
        params: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Route parameters based on their descriptors."""
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
        
        # Add positional prompt parameters in order
        prompt_params.sort(key=lambda x: x[0])
        for _, name, value in prompt_params:
            routed["prompt"][name] = value
        
        return routed
    
    async def _build_prompt(self, prompt_params: Dict[str, Any]) -> str:
        """Build prompt from parameters."""
        # Extract standard prompt components
        instructions = prompt_params.get("instructions", "")
        output_format = prompt_params.get("output_format", "")
        context = prompt_params.get("context", [])
        
        # Build prompt using existing utility
        prompt, _ = await asyncio.to_thread(
            build_prompt,
            instructions,
            output_format,
            context,
            None  # Attachments handled separately via vector store
        )
        
        return prompt
    
    async def _create_vector_store(self, files: List[str]) -> Optional[str]:
        """Create vector store from files."""
        if not files:
            return None
            
        try:
            vs_id = await asyncio.to_thread(create_vector_store, files)
            if vs_id:
                logger.info(f"Created vector store: {vs_id}")
            return vs_id
        except Exception as e:
            logger.error(f"Error creating vector store: {e}")
            return None


# Global executor instance
executor = ToolExecutor()
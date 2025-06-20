"""Executor for dataclass-based tools."""
import asyncio
import logging
from typing import Dict, Any, Optional
from ..adapters import get_adapter
from ..session_cache import session_cache
from .registry import ToolMetadata
from .base import ToolSpec
from .vector_store_manager import vector_store_manager
from .prompt_engine import prompt_engine
from .parameter_validator import ParameterValidator
from .parameter_router import ParameterRouter

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Orchestrates tool execution using specialized components."""
    
    def __init__(self, strict_mode: bool = False):
        """Initialize executor with component instances.
        
        Args:
            strict_mode: If True, raise errors for unknown parameters.
                        If False (default), log warnings only.
        """
        self.validator = ParameterValidator(strict_mode)
        self.router = ParameterRouter()
        self.prompt_engine = prompt_engine
        self.vector_store_manager = vector_store_manager
    
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
        vs_id: Optional[str] = None  # Initialize to avoid UnboundLocalError
        
        try:
            # 1. Create tool instance and validate inputs
            tool_instance = metadata.spec_class()
            validated_params = self.validator.validate(tool_instance, metadata, kwargs)
            
            # 2. Route parameters
            routed_params = self.router.route(metadata, validated_params)
            
            # 3. Build prompt
            prompt = await self.prompt_engine.build(metadata.spec_class, routed_params["prompt"])
            
            # 4. Handle vector store if needed
            vs_id = None
            vector_store_ids = None
            if routed_params["vector_store"]:
                vs_id = await self.vector_store_manager.create(routed_params["vector_store"])
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
                await vector_store_manager.delete(vs_id)
            
            elapsed = asyncio.get_event_loop().time() - start_time
            logger.info(f"{tool_id} completed in {elapsed:.2f}s")
    
    


# Global executor instance
# Set strict_mode=True if you want to reject unknown parameters
executor = ToolExecutor(strict_mode=False)
"""Executor for dataclass-based tools."""

import asyncio
import logging
from typing import Optional, List
from mcp_second_brain import adapters
from mcp_second_brain import session_cache as session_cache_module
from mcp_second_brain import gemini_session_cache as gemini_session_cache_module
from .registry import ToolMetadata
from .vector_store_manager import vector_store_manager
from .prompt_engine import prompt_engine
from .parameter_validator import ParameterValidator
from .parameter_router import ParameterRouter

# Project memory imports
from ..memory import store_conversation_memory
from ..config import get_settings

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
        if metadata is None:
            raise ValueError("Tool metadata is None - tool not found in registry")

        start_time = asyncio.get_event_loop().time()
        tool_id = metadata.id
        vs_id: Optional[str] = None  # Initialize to avoid UnboundLocalError
        memory_tasks: List[asyncio.Task] = []  # Track memory storage tasks

        try:
            # 1. Create tool instance and validate inputs
            tool_instance = metadata.spec_class()
            validated_params = self.validator.validate(tool_instance, metadata, kwargs)

            # 2. Route parameters
            routed_params = self.router.route(metadata, validated_params)

            # 3. Build prompt
            prompt_params = routed_params["prompt"]
            assert isinstance(prompt_params, dict)  # Type hint for mypy
            prompt = await self.prompt_engine.build(metadata.spec_class, prompt_params)

            # 4. Handle vector store if needed
            vs_id = None
            vector_store_ids = None
            vector_store_param = routed_params["vector_store"]
            assert isinstance(vector_store_param, list)  # Type hint for mypy
            if vector_store_param:
                # Gather files from directories
                from ..utils.fs import gather_file_paths

                files = gather_file_paths(vector_store_param)
                if files:
                    vs_id = await self.vector_store_manager.create(files)
                    vector_store_ids = [vs_id] if vs_id else None

            # Memory stores are no longer auto-attached
            # Models should use search_project_memory function to access memory

            # 5. Get adapter
            settings = get_settings()
            adapter, error = adapters.get_adapter(
                metadata.model_config["adapter_class"],
                metadata.model_config["model_name"],
            )
            if not adapter:
                return f"Error: Failed to initialize adapter: {error}"

            # 6. Handle session
            previous_response_id = None
            gemini_messages = None
            session_params = routed_params["session"]
            assert isinstance(session_params, dict)  # Type hint for mypy
            session_id = session_params.get("session_id")
            if session_id:
                if metadata.model_config["adapter_class"] == "openai":
                    previous_response_id = (
                        session_cache_module.session_cache.get_response_id(session_id)
                    )
                    if previous_response_id:
                        logger.info(f"Continuing session {session_id}")
                elif metadata.model_config["adapter_class"] == "vertex":
                    gemini_messages = (
                        gemini_session_cache_module.gemini_session_cache.get_messages(
                            session_id
                        )
                    )

            # 7. Execute model call
            adapter_params = routed_params["adapter"]
            assert isinstance(adapter_params, dict)  # Type hint for mypy
            if previous_response_id:
                adapter_params["previous_response_id"] = previous_response_id

            if gemini_messages is not None:
                adapter_params["messages"] = gemini_messages + [
                    {"role": "user", "content": prompt}
                ]

            result = await asyncio.wait_for(
                adapter.generate(
                    prompt=prompt,
                    vector_store_ids=vector_store_ids,
                    timeout=metadata.model_config["timeout"],
                    **adapter_params,
                ),
                timeout=metadata.model_config["timeout"],
            )

            # 8. Handle response
            if isinstance(result, dict):
                content = result.get("content", "")
                if (
                    session_id
                    and metadata.model_config["adapter_class"] == "openai"
                    and "response_id" in result
                ):
                    session_cache_module.session_cache.set_response_id(
                        session_id, result["response_id"]
                    )
                if session_id and metadata.model_config["adapter_class"] == "vertex":
                    try:
                        gemini_session_cache_module.gemini_session_cache.append_exchange(
                            session_id, prompt, content
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update Gemini session: {e}")

                # 8a. Store conversation in memory
                if settings.memory_enabled and session_id:
                    try:
                        # Extract messages from prompt
                        messages = prompt_params.get("messages", [])
                        task = asyncio.create_task(
                            store_conversation_memory(
                                session_id=session_id,
                                tool_name=tool_id,
                                messages=messages,
                                response=content,
                            )
                        )
                        memory_tasks.append(task)
                    except Exception as e:
                        logger.warning(f"Failed to store conversation memory: {e}")

                return str(content)
            else:
                # Vertex adapter returns string directly
                # Store conversation for Vertex models too
                if settings.memory_enabled and session_id:
                    try:
                        messages = prompt_params.get("messages", [])
                        task = asyncio.create_task(
                            store_conversation_memory(
                                session_id=session_id,
                                tool_name=tool_id,
                                messages=messages,
                                response=result,
                            )
                        )
                        memory_tasks.append(task)
                    except Exception as e:
                        logger.warning(f"Failed to store conversation memory: {e}")

                if session_id and metadata.model_config["adapter_class"] == "vertex":
                    try:
                        gemini_session_cache_module.gemini_session_cache.append_exchange(
                            session_id, prompt, str(result)
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update Gemini session: {e}")

                return str(result)

        finally:
            # Cleanup
            if vs_id:
                await vector_store_manager.delete(vs_id)

            # Wait for memory tasks to complete
            if memory_tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*memory_tasks, return_exceptions=True),
                        timeout=120.0,  # 120 second timeout for memory storage (vector indexing can take 10-30s)
                    )
                except asyncio.TimeoutError:
                    logger.warning("Memory storage tasks timed out")

            elapsed = asyncio.get_event_loop().time() - start_time
            logger.info(f"{tool_id} completed in {elapsed:.2f}s")


# Global executor instance
# Set strict_mode=True if you want to reject unknown parameters
executor = ToolExecutor(strict_mode=False)

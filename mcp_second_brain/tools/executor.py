"""Executor for dataclass-based tools."""

import asyncio
import logging
from typing import Optional, List, Dict, Any
import fastmcp.exceptions
from mcp_second_brain import adapters
from mcp_second_brain import session_cache as session_cache_module
from mcp_second_brain import gemini_session_cache as gemini_session_cache_module
from mcp_second_brain import grok_session_cache as grok_session_cache_module
from .registry import ToolMetadata
from .vector_store_manager import vector_store_manager
from .prompt_engine import prompt_engine
from .parameter_validator import ParameterValidator
from .parameter_router import ParameterRouter

# Project memory imports
from ..memory import store_conversation_memory
from ..config import get_settings
from ..utils.redaction import redact_secrets

# Stable list imports
from ..utils.context_builder import build_context_with_stable_list
from ..utils.stable_list_cache import StableListCache
from ..adapters.model_registry import get_model_context_window
from lxml import etree as ET

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

            # Get session info
            session_params = routed_params["session"]
            assert isinstance(session_params, dict)  # Type hint for mypy
            session_id = session_params.get("session_id")

            # Use stable-inline list for context management
            settings = get_settings()

            # Session ID is required for stable list functionality
            if session_id:
                logger.info(f"Using stable-inline list for session {session_id}")

                # Initialize cache
                cache = StableListCache()

                # Calculate token budget
                model_name = metadata.model_config["model_name"]
                model_limit = get_model_context_window(model_name)
                context_percentage = settings.mcp.context_percentage
                safety_margin = 2000  # Consistent with old builder
                token_budget = max(
                    int(model_limit * context_percentage) - safety_margin, 1000
                )

                # Get context and attachment paths
                context_paths = prompt_params.get("context", [])
                attachment_paths_raw = routed_params.get("vector_store", [])
                # Ensure it's a list
                attachment_paths = (
                    attachment_paths_raw
                    if isinstance(attachment_paths_raw, list)
                    else []
                )

                # Call the new context builder
                inline_files, overflow_files = await build_context_with_stable_list(
                    context_paths=context_paths,
                    session_id=session_id,
                    cache=cache,
                    token_budget=token_budget,
                    attachments=attachment_paths,
                )

                # Format the prompt with inline files
                task = ET.Element("Task")
                ET.SubElement(task, "Instructions").text = prompt_params.get(
                    "instructions", ""
                )
                ET.SubElement(task, "OutputFormat").text = prompt_params.get(
                    "output_format", ""
                )
                CTX = ET.SubElement(task, "CONTEXT")

                # Helper function to create file elements
                def _create_file_element(path: str, content: str) -> Any:
                    el = ET.Element("file", path=path)
                    safe_content = "".join(
                        c for c in content if ord(c) >= 32 or c in "\t\n\r"
                    )
                    el.text = safe_content
                    return el

                for path, content, _ in inline_files:
                    CTX.append(_create_file_element(path, content))

                prompt = ET.tostring(task, encoding="unicode")
                if overflow_files:
                    prompt += "\n\nYou have additional information accessible through the file search tool."

                # Store overflow files for vector store creation
                files_for_vector_store = overflow_files
            else:
                # Fallback for cases without session_id (backwards compatibility)
                logger.info(
                    "No session_id provided, using original prompt engine for backwards compatibility"
                )
                prompt = await self.prompt_engine.build(
                    metadata.spec_class, prompt_params
                )
                files_for_vector_store = None

            # Include developer/system prompt for assistant models
            from ..prompts import get_developer_prompt

            model_name = metadata.model_config["model_name"]
            adapter_class = metadata.model_config["adapter_class"]
            developer_prompt = get_developer_prompt(model_name)

            messages: Optional[List[Dict[str, Any]]] = None
            final_prompt = prompt

            if adapter_class == "openai":
                # OpenAI Responses API supports developer role
                messages = [
                    {"role": "developer", "content": developer_prompt},
                    {"role": "user", "content": prompt},
                ]
                adapter_params = routed_params["adapter"]
                assert isinstance(adapter_params, dict)  # Type hint for mypy
                adapter_params["messages"] = messages
                # Store messages for conversation memory
                prompt_params["messages"] = messages
            elif adapter_class == "vertex":
                # Gemini models - use system_instruction parameter
                adapter_params = routed_params["adapter"]
                assert isinstance(adapter_params, dict)  # Type hint for mypy
                adapter_params["system_instruction"] = developer_prompt
                # Store messages for conversation memory
                messages = [
                    {"role": "system", "content": developer_prompt},
                    {"role": "user", "content": prompt},
                ]
                prompt_params["messages"] = messages
            else:
                # Unknown adapter - use safe default of prepending
                final_prompt = f"{developer_prompt}\n\n{prompt}"
                # Store messages for conversation memory
                messages = [
                    {"role": "system", "content": developer_prompt},
                    {"role": "user", "content": prompt},
                ]
                prompt_params["messages"] = messages

            # 4. Handle vector store if needed
            vs_id = None
            vector_store_ids = None

            if session_id and files_for_vector_store:
                # Use pre-calculated overflow files from stable list
                # Clear attachment search cache for new attachments
                from .search_attachments import SearchAttachmentAdapter

                await SearchAttachmentAdapter.clear_deduplication_cache()
                logger.info(
                    "Cleared SearchAttachmentAdapter deduplication cache for new attachments"
                )

                logger.info(
                    f"Creating vector store with {len(files_for_vector_store)} overflow/attachment files: {files_for_vector_store}"
                )
                vs_id = await self.vector_store_manager.create(files_for_vector_store)
                vector_store_ids = [vs_id] if vs_id else None
                logger.info(
                    f"Created vector store {vs_id}, vector_store_ids={vector_store_ids}"
                )
            else:
                # Fallback: Gather files from vector_store parameter if no session_id
                vector_store_param = routed_params.get("vector_store", [])
                assert isinstance(vector_store_param, list)  # Type hint for mypy
                if vector_store_param:
                    # Clear attachment search cache for new attachments
                    from .search_attachments import SearchAttachmentAdapter

                    await SearchAttachmentAdapter.clear_deduplication_cache()
                    logger.info(
                        "Cleared SearchAttachmentAdapter deduplication cache for new attachments"
                    )

                    # Gather files from directories (skip safety check for attachments)
                    from ..utils.fs import gather_file_paths

                    files = gather_file_paths(
                        vector_store_param, skip_safety_check=True
                    )
                    logger.info(
                        f"Gathered {len(files)} files from attachments: {files}"
                    )
                    if files:
                        vs_id = await self.vector_store_manager.create(files)
                        vector_store_ids = [vs_id] if vs_id else None
                        logger.info(
                            f"Created vector store {vs_id}, vector_store_ids={vector_store_ids}"
                        )

            # Memory stores are no longer auto-attached
            # Models should use search_project_memory function to access memory

            # 5. Get adapter
            settings = get_settings()
            adapter, error = adapters.get_adapter(
                metadata.model_config["adapter_class"],
                metadata.model_config["model_name"],
            )
            if not adapter:
                raise fastmcp.exceptions.ToolError(
                    f"Failed to initialize adapter: {error}"
                )

            # 6. Handle session
            previous_response_id = None
            gemini_messages = None
            grok_messages = None  # NEW
            session_params = routed_params["session"]
            assert isinstance(session_params, dict)  # Type hint for mypy
            session_id = session_params.get("session_id")
            if session_id:
                if metadata.model_config["adapter_class"] == "openai":
                    previous_response_id = (
                        await session_cache_module.session_cache.get_response_id(
                            session_id
                        )
                    )
                    if previous_response_id:
                        logger.info(f"Continuing session {session_id}")
                elif metadata.model_config["adapter_class"] == "vertex":
                    gemini_messages = await gemini_session_cache_module.gemini_session_cache.get_history(
                        session_id
                    )
                # --- NEW: Handle Grok sessions ---
                elif metadata.model_config["adapter_class"] == "xai":
                    grok_messages = (
                        await grok_session_cache_module.grok_session_cache.get_history(
                            session_id
                        )
                    )
                    logger.info(
                        f"Continuing Grok session {session_id} with {len(grok_messages)} messages"
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

            # --- NEW: Pass Grok history ---
            if grok_messages:
                adapter_params["messages"] = grok_messages

            # Merge structured_output parameters into adapter params
            structured_output_params = routed_params.get("structured_output", {})
            assert isinstance(structured_output_params, dict)
            adapter_params.update(structured_output_params)

            explicit_vs_ids = routed_params.get("vector_store_ids")
            assert isinstance(explicit_vs_ids, list)
            if explicit_vs_ids:
                vector_store_ids = (vector_store_ids or []) + list(explicit_vs_ids)

            result = await asyncio.wait_for(
                adapter.generate(
                    prompt=final_prompt,
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
                    await session_cache_module.session_cache.set_response_id(
                        session_id, result["response_id"]
                    )
                # Session management is now handled inside the adapters themselves
                # No need to save sessions here for Vertex/Grok models

                # Redact secrets from content
                redacted_content = redact_secrets(str(content))

                # 8a. Store conversation in memory (with redacted content)
                if settings.memory_enabled and session_id:
                    try:
                        # Extract messages from prompt
                        conv_messages = prompt_params.get("messages", [])
                        if not isinstance(conv_messages, list):
                            conv_messages = []
                        memory_task = asyncio.create_task(
                            store_conversation_memory(
                                session_id=session_id,
                                tool_name=tool_id,
                                messages=conv_messages,
                                response=redacted_content,
                            )
                        )
                        memory_tasks.append(memory_task)
                    except Exception as e:
                        logger.warning(f"Failed to store conversation memory: {e}")

                return redacted_content
            else:
                # Redact secrets from result
                redacted_result = redact_secrets(str(result))

                # Store conversation for Vertex models too (with redacted content)
                if settings.memory_enabled and session_id:
                    try:
                        conv_messages = prompt_params.get("messages", [])
                        if not isinstance(conv_messages, list):
                            conv_messages = []
                        memory_task = asyncio.create_task(
                            store_conversation_memory(
                                session_id=session_id,
                                tool_name=tool_id,
                                messages=conv_messages,
                                response=redacted_result,
                            )
                        )
                        memory_tasks.append(memory_task)
                    except Exception as e:
                        logger.warning(f"Failed to store conversation memory: {e}")

                # Session management is now handled inside the adapters themselves
                # No need to save sessions here for Vertex/Grok models

                return redacted_result

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

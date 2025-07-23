"""Executor for dataclass-based tools."""

import asyncio
import contextlib
import logging
import time
import uuid
from typing import Optional, List, Dict, Any
import fastmcp.exceptions
from mcp_second_brain import adapters
from mcp_second_brain import session_cache as session_cache_module
from mcp_second_brain import gemini_session_cache as gemini_session_cache_module
from .registry import ToolMetadata
from .vector_store_manager import vector_store_manager
from .prompt_engine import prompt_engine
from .parameter_validator import ParameterValidator
from .parameter_router import ParameterRouter
from ..utils.scope_manager import scope_manager

# Import debug logger

# Project history imports
from .safe_memory import safe_store_conversation_memory
from ..config import get_settings
from ..utils.redaction import redact_secrets
from ..operation_manager import operation_manager

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
        # Create unique operation ID early for consistent logging
        operation_id = f"{tool_id}_{uuid.uuid4().hex[:8]}"

        # Log request start with operation ID
        logger.info(f"[{operation_id}] Starting {tool_id}")

        vs_id: Optional[str] = None  # Initialize to avoid UnboundLocalError
        memory_tasks: List[asyncio.Task] = []  # Track memory storage tasks
        was_cancelled = False  # Track if the operation was cancelled

        try:
            # 1. Create tool instance and validate inputs
            logger.debug(f"[STEP 1] Creating tool instance for {tool_id}")
            tool_instance = metadata.spec_class()
            validated_params = self.validator.validate(tool_instance, metadata, kwargs)

            # E2E verbose logging - log input parameters when DEBUG is enabled
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[{operation_id}] Input parameters: {validated_params}")

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
                logger.debug(f"Using stable-inline list for session {session_id}")

                # Initialize cache
                cache = StableListCache()

                # Calculate token budget
                model_name = metadata.model_config["model_name"]
                model_limit = get_model_context_window(model_name)
                context_percentage = settings.mcp.context_percentage

                # The context_percentage (default 0.85) already includes safety margin
                # The remaining 15% is for system prompts, tool responses, etc.
                token_budget = max(int(model_limit * context_percentage), 1000)
                logger.debug(
                    f"[TOKEN_BUDGET] Model: {model_name}, limit: {model_limit:,}, "
                    f"percentage: {context_percentage:.0%}, "
                    f"budget: {token_budget:,}"
                )

                # Get context and priority_context paths
                logger.debug("[STEP 7] Getting context and priority_context paths")
                context_paths = prompt_params.get("context", [])
                priority_context_paths = prompt_params.get("priority_context", [])
                logger.debug(
                    f"[STEP 7.1] Context paths: {len(context_paths)}, Priority context paths: {len(priority_context_paths)}"
                )

                # Call the new context builder
                logger.debug("[STEP 8] Calling context builder with stable list")
                (
                    inline_files,
                    overflow_files,
                    file_tree,
                ) = await build_context_with_stable_list(
                    context_paths=context_paths,
                    session_id=session_id,
                    cache=cache,
                    token_budget=token_budget,
                    priority_context=priority_context_paths,
                )
                logger.debug(
                    f"[STEP 8.1] Context builder returned: {len(inline_files)} inline files, {len(overflow_files)} overflow files, file tree generated"
                )

                # Format the prompt with inline files
                logger.debug("[STEP 9] Formatting prompt with inline files")
                task = ET.Element("Task")
                ET.SubElement(task, "Instructions").text = prompt_params.get(
                    "instructions", ""
                )
                ET.SubElement(task, "OutputFormat").text = prompt_params.get(
                    "output_format", ""
                )

                # Add file map with legend
                file_map = ET.SubElement(task, "file_map")
                file_map.text = (
                    file_tree
                    + "\n\nLegend: Files marked 'attached' are available via search_task_files. Unmarked files are included below."
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
                logger.debug(f"[STEP 9.1] Prompt built: {len(prompt)} chars")
                if overflow_files:
                    prompt += "\n\n<instructions_on_use>The files in the file tree but not included in <CONTEXT> you access via the search_task_files MCP function. They are stored in a vector database and the search function does semantic search.</instructions_on_use>"

                # Store overflow files for vector store creation
                files_for_vector_store = overflow_files
            else:
                # Fallback for cases without session_id (backwards compatibility)
                logger.debug(
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

                # ALWAYS send the developer prompt so the model maintains its role
                # across the entire session. Gemini deduplicates identical system
                # instructions, so this is safe and necessary.
                adapter_params["system_instruction"] = developer_prompt

                # Since session_id is mandatory, we always have a session
                # The adapter will handle loading history and adding the new message
                session_id = session_params.get("session_id")
                logger.debug(f"Vertex adapter will handle session {session_id}")
            elif adapter_class == "xai":
                # Grok models - use system message in messages array (OpenAI format)
                # Note: For sessions, Grok adapter will manage history itself
                messages = [
                    {"role": "system", "content": developer_prompt},
                    {"role": "user", "content": prompt},
                ]
                adapter_params = routed_params["adapter"]
                assert isinstance(adapter_params, dict)  # Type hint for mypy
                adapter_params["messages"] = messages
                # Store messages for conversation memory
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
                from .search_task_files import SearchTaskFilesAdapter

                await SearchTaskFilesAdapter.clear_deduplication_cache()
                logger.debug(
                    "Cleared SearchTaskFilesAdapter deduplication cache for new task files"
                )

                logger.debug(
                    f"Creating vector store with {len(files_for_vector_store)} overflow/attachment files: {files_for_vector_store}"
                )
                vs_id = await self.vector_store_manager.create(
                    files_for_vector_store, session_id=session_id
                )
                vector_store_ids = [vs_id] if vs_id else None
                logger.debug(
                    f"Vector store ready: {vs_id}, vector_store_ids={vector_store_ids}"
                )

                # E2E verbose logging - log vector store details when DEBUG is enabled
                if logger.isEnabledFor(logging.DEBUG) and vs_id:
                    logger.debug(
                        f"[{operation_id}] Created vector store {vs_id} with {len(files_for_vector_store)} files for session {session_id}"
                    )
                logger.debug("[DEBUG] Exiting IF block for vector store handling")
            else:
                # Fallback: Gather files from vector_store parameter if no session_id
                vector_store_param = routed_params.get("vector_store", [])
                assert isinstance(vector_store_param, list)  # Type hint for mypy
                if vector_store_param:
                    # Clear attachment search cache for new attachments
                    from .search_task_files import SearchTaskFilesAdapter

                    await SearchTaskFilesAdapter.clear_deduplication_cache()
                    logger.debug(
                        "Cleared SearchTaskFilesAdapter deduplication cache for new attachments"
                    )

                    # Gather files from directories (skip safety check for attachments)
                    from ..utils.fs import gather_file_paths

                    files = gather_file_paths(
                        vector_store_param, skip_safety_check=True
                    )
                    logger.debug(
                        f"Gathered {len(files)} files from attachments: {files}"
                    )
                    if files:
                        vs_id = await self.vector_store_manager.create(
                            files, session_id=None
                        )
                        vector_store_ids = [vs_id] if vs_id else None
                        logger.debug(
                            f"Created vector store {vs_id}, vector_store_ids={vector_store_ids}"
                        )

            # Memory stores are no longer auto-attached
            # Models should use search_project_history function to access memory

            # 5. Get adapter
            logger.debug("[DEBUG] About to get settings")
            settings = get_settings()
            logger.debug("[DEBUG] About to get adapter")
            adapter, error = adapters.get_adapter(
                metadata.model_config["adapter_class"],
                metadata.model_config["model_name"],
            )
            logger.debug(f"[DEBUG] Got adapter: {adapter}")
            if not adapter:
                raise fastmcp.exceptions.ToolError(
                    f"Failed to initialize adapter: {error}"
                )

            # 6. Handle session
            previous_response_id = None
            gemini_messages = None
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
                        logger.debug(f"Continuing session {session_id}")
                elif metadata.model_config["adapter_class"] == "vertex":
                    # Vertex adapter expects List[Dict[str, str]]; use the helper that
                    # already converts Gemini Content objects into this format.
                    gemini_messages = await gemini_session_cache_module.gemini_session_cache.get_messages(
                        session_id
                    )
                # Note: Grok (xai) adapter handles its own session loading

            # 7. Execute model call
            logger.debug("[STEP 14] Preparing to execute model call")
            adapter_params = routed_params["adapter"]
            assert isinstance(adapter_params, dict)  # Type hint for mypy

            # FIX: Merge session parameters into adapter parameters
            session_params = routed_params.get("session", {})
            adapter_params.update(session_params)

            if previous_response_id:
                adapter_params["previous_response_id"] = previous_response_id

            if gemini_messages is not None:
                adapter_params["messages"] = gemini_messages + [
                    {"role": "user", "content": prompt}
                ]

            # Merge structured_output parameters into adapter params
            structured_output_params = routed_params.get("structured_output", {})
            assert isinstance(structured_output_params, dict)
            adapter_params.update(structured_output_params)

            # TODO: This adapter-specific translation should be moved into each adapter's
            # generate() method for better separation of concerns
            schema_str = structured_output_params.get("structured_output_schema")
            if schema_str is not None:
                # Parse the JSON string to dict
                try:
                    import json

                    schema = (
                        json.loads(schema_str)
                        if isinstance(schema_str, str)
                        else schema_str
                    )
                except (json.JSONDecodeError, ValueError) as e:
                    raise ValueError(f"Invalid JSON in structured_output_schema: {e}")

                adapter_class = metadata.model_config["adapter_class"]
                if adapter_class == "openai":
                    # OpenAI adapter handles structured_output_schema internally
                    # Just ensure it's passed through as dict
                    adapter_params["structured_output_schema"] = schema
                elif adapter_class == "vertex":
                    # Pass the original JSON schema - let the adapter handle conversion
                    adapter_params["structured_output_schema"] = schema
                elif adapter_class == "xai":
                    # xAI/Grok format
                    adapter_params["output_schema"] = schema
                    adapter_params["format"] = "json"
                    # Remove the generic key since xAI uses different parameters
                    adapter_params.pop("structured_output_schema", None)

            # Merge prompt parameters for adapters that need them (e.g., SearchHistoryAdapter)
            # Don't include 'prompt' itself as it's passed as positional arg
            # Don't include 'messages' either if we've already set it from session handling
            prompt_params_for_adapter = {
                k: v
                for k, v in prompt_params.items()
                if k != "prompt"
                and (k != "messages" or "messages" not in adapter_params)
            }
            adapter_params.update(prompt_params_for_adapter)

            # Pass session_id to the adapter so it can propagate to built-in tools
            if session_id:
                adapter_params["session_id"] = session_id
                logger.debug(
                    f"[EXECUTOR] Added session_id to adapter_params: {session_id}"
                )

            explicit_vs_ids = routed_params.get("vector_store_ids")
            assert isinstance(explicit_vs_ids, list)
            if explicit_vs_ids:
                vector_store_ids = (vector_store_ids or []) + list(explicit_vs_ids)

            timeout_seconds = metadata.model_config["timeout"]
            adapter_start_time = time.time()
            logger.debug(
                f"[STEP 15] Calling adapter.generate with prompt {len(final_prompt)} chars, vector_store_ids={vector_store_ids}, timeout={timeout_seconds}s"
            )
            logger.debug(
                f"[TIMING] Starting adapter.generate at {time.strftime('%H:%M:%S')}"
            )

            # Renew lease before long-running operation if using Loiter Killer
            if session_id and vs_id and self.vector_store_manager.loiter_killer.enabled:
                await self.vector_store_manager.loiter_killer.renew_lease(session_id)
                logger.debug(f"Renewed Loiter Killer lease for session {session_id}")

            # Set the scope context for this request
            async with scope_manager.scope(session_id):
                try:
                    result = await operation_manager.run_with_timeout(
                        operation_id,
                        adapter.generate(
                            prompt=final_prompt,
                            vector_store_ids=vector_store_ids,
                            timeout=timeout_seconds,
                            **adapter_params,
                        ),
                        timeout=timeout_seconds,
                    )

                    end_time = time.time()
                    duration = end_time - adapter_start_time
                    logger.debug(
                        f"[STEP 16] adapter.generate completed in {duration:.2f}s, result type: {type(result)}, length: {len(str(result)) if result else 0}"
                    )
                    logger.debug(
                        f"[TIMING] Completed adapter.generate at {time.strftime('%H:%M:%S')}"
                    )

                    # E2E verbose logging - log model response when DEBUG is enabled
                    if logger.isEnabledFor(logging.DEBUG):
                        # Truncate very long responses for logging
                        response_str = str(result)
                        if len(response_str) > 1000:
                            response_preview = (
                                response_str[:500] + "..." + response_str[-500:]
                            )
                        else:
                            response_preview = response_str
                        logger.debug(
                            f"[{operation_id}] Model response preview: {response_preview}"
                        )
                except asyncio.TimeoutError:
                    timeout_time = time.time()
                    partial_duration = timeout_time - adapter_start_time
                    logger.error(
                        f"[{operation_id}] [CRITICAL] Adapter timeout after {timeout_seconds}s for {tool_id} (actual duration: {partial_duration:.2f}s)"
                    )
                    raise fastmcp.exceptions.ToolError(
                        f"Tool execution timed out after {timeout_seconds} seconds"
                    )
                except asyncio.CancelledError:
                    was_cancelled = True
                    logger.warning(
                        f"[{operation_id}] [CANCEL] {tool_id} received CancelledError in executor"
                    )
                    logger.debug(
                        f"[CANCEL] Active tasks in executor: {len(asyncio.all_tasks())}"
                    )
                    logger.debug(f"[CANCEL] Vector store IDs were: {vector_store_ids}")
                    logger.debug(f"[CANCEL] Session ID was: {session_id}")
                    logger.debug(f"[CANCEL] Adapter was: {adapter_class}")
                    logger.debug("[CANCEL] Re-raising CancelledError from executor")
                    raise  # Important: do NOT convert or return
                except Exception as e:
                    logger.error(
                        f"[{operation_id}] [CRITICAL] Adapter generate failed for {tool_id}: {e}"
                    )
                    raise

            # 8. Handle response
            logger.debug("[STEP 17] Handling response")
            if isinstance(result, dict):
                logger.debug("[STEP 17.1] Result is dict")
                content = result.get("content", "")
                logger.debug(f"[STEP 17.2] Got content, length: {len(str(content))}")
                if (
                    session_id
                    and metadata.model_config["adapter_class"] == "openai"
                    and "response_id" in result
                ):
                    logger.debug(
                        f"[STEP 17.3] Saving response_id for session {session_id}"
                    )
                    await session_cache_module.session_cache.set_response_id(
                        session_id, result["response_id"]
                    )
                    logger.debug("[STEP 17.4] Response_id saved")
                # Session management is now handled inside the adapters themselves
                # No need to save sessions here for Vertex/Grok models

                # Redact secrets from content
                logger.debug("[STEP 17.5] Starting redaction")
                redacted_content = redact_secrets(str(content))
                logger.debug("[STEP 17.6] Redaction complete")

                # 8a. Store conversation in memory (with redacted content)
                if settings.memory_enabled and session_id:
                    try:
                        # Extract messages from prompt
                        conv_messages = prompt_params.get("messages", [])
                        if not isinstance(conv_messages, list):
                            conv_messages = []
                        # Re-enabled: Memory storage is important for context
                        logger.debug(
                            f"[MEMORY] Creating background memory storage task for {tool_id}"
                        )
                        memory_task = asyncio.create_task(
                            safe_store_conversation_memory(
                                session_id=session_id,
                                tool_name=tool_id,
                                messages=conv_messages,
                                response=redacted_content,
                            )
                        )
                        memory_tasks.append(memory_task)
                    except Exception as e:
                        logger.warning(f"Failed to store conversation memory: {e}")

                logger.debug(
                    f"[STEP 17.7] About to return redacted content, length: {len(redacted_content)}"
                )
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
                        # Re-enabled: Memory storage is important for context
                        memory_task = asyncio.create_task(
                            safe_store_conversation_memory(
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

        except asyncio.CancelledError:
            # Handle cancellation that happens outside the inner try block
            # (e.g., during vector store creation)
            was_cancelled = True
            logger.warning(
                f"[{operation_id}] [CANCEL] {tool_id} received CancelledError in outer executor block"
            )
            logger.debug("[CANCEL] Re-raising CancelledError from outer block")
            raise
        except Exception as e:
            # If cancellation already happened, don't let a subsequent error in the
            # cleanup logic cause a crash.
            if was_cancelled:
                logger.debug(f"Ignoring error after cancellation for {tool_id}: {e}")
                return ""

            logger.error(
                f"[{operation_id}] [CRITICAL] Tool execution failed for {tool_id}: {e}"
            )
            import traceback

            logger.error(
                f"[{operation_id}] [CRITICAL] Traceback: {traceback.format_exc()}"
            )
            # Re-raise as ToolError for proper MCP error handling
            raise fastmcp.exceptions.ToolError(f"Tool execution failed: {str(e)}")

        finally:
            logger.debug(f"[CANCEL] In finally block, was_cancelled={was_cancelled}")
            logger.debug(
                f"[CANCEL] Active tasks in finally: {len(asyncio.all_tasks())}"
            )

            # If operation was cancelled, do NOT block on more awaits
            if was_cancelled:
                logger.debug(f"[CANCEL] Handling cancelled cleanup for {tool_id}")
                # Fast exit - schedule best-effort background cleanup
                if vs_id:
                    # TEMPORARILY DISABLED: Testing if vector store deletion causes hanging
                    logger.debug(
                        f"[TEST] Skipping vector store deletion for {vs_id} (cancelled path)"
                    )
                    # async def safe_cleanup():
                    #     try:
                    #         await vector_store_manager.delete(vs_id)
                    #     except Exception as e:
                    #         logger.debug(f"Background cleanup failed (expected): {e}")
                    #
                    # # Re-enabled: Background cleanup for vector stores
                    # bg_task = asyncio.create_task(safe_cleanup())
                    # # Mark exception as retrieved to prevent ExceptionGroup
                    # bg_task.add_done_callback(lambda t: t.exception())
                # Cancel memory tasks to free resources
                logger.debug(
                    f"[MEMORY] Cancelling {len(memory_tasks)} memory storage tasks due to operation cancellation"
                )
                for task in memory_tasks:  # type: ignore[assignment]
                    task.cancel()  # type: ignore[attr-defined]
                    # Mark exception as retrieved to prevent ExceptionGroup
                    task.add_done_callback(lambda t: t.exception())  # type: ignore[attr-defined]
                logger.debug(f"{tool_id} cancelled - cleanup scheduled in background")
                # DON'T return empty string - this prevents proper error handling!

            # Normal path (no cancellation) - safe to await with timeouts
            if vs_id:
                # TEMPORARILY DISABLED: Testing if vector store deletion causes hanging
                logger.debug(
                    f"[TEST] Skipping vector store deletion for {vs_id} (normal path)"
                )
                # # Add timeout to avoid hanging on cleanup
                # with contextlib.suppress(asyncio.TimeoutError):
                #     await asyncio.wait_for(
                #         vector_store_manager.delete(vs_id), timeout=5.0
                #     )

            # Wait for memory tasks to complete
            if memory_tasks:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        asyncio.gather(*memory_tasks, return_exceptions=True),
                        timeout=120.0,  # Original timeout for memory storage
                    )

            elapsed = asyncio.get_event_loop().time() - start_time
            logger.info(f"[{operation_id}] {tool_id} completed in {elapsed:.2f}s")


# Global executor instance
# Set strict_mode=True if you want to reject unknown parameters
executor = ToolExecutor(strict_mode=False)

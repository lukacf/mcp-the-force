"""Executor for dataclass-based tools."""

import asyncio
import logging
import time
import uuid
from typing import Optional, List, Any, Union, Dict
import fastmcp.exceptions
from mcp_the_force.adapters.registry import get_adapter_class
from .registry import ToolMetadata
from ..vectorstores.manager import vector_store_manager
from .prompt_engine import prompt_engine
from .parameter_validator import ParameterValidator
from .parameter_router import ParameterRouter
from .capability_validator import CapabilityValidator
# Scope management is now handled at the integration layer

# Import debug logger

# Project history imports
from .safe_history import safe_record_conversation
from ..config import get_settings
from ..utils.redaction import redact_secrets
from ..operation_manager import operation_manager

# Context builder import

# Context window now comes from tool metadata, no central registry needed

logger = logging.getLogger(__name__)


async def _maybe_store_memory(
    session_id: str,
    tool_id: str,
    messages: List[Dict[str, Any]],
    response: str,
    disable_history_record: bool,
    memory_tasks: List[asyncio.Task],
) -> None:
    """Store conversation memory either synchronously or asynchronously based on settings."""
    if disable_history_record:
        return

    settings = get_settings()
    if not settings.history_enabled:
        return

    if settings.history.sync:
        # Block (with timeout) so the CLI process can exit safely afterwards
        logger.debug(
            f"[MEMORY] Storing conversation memory synchronously for {tool_id}"
        )
        try:
            await asyncio.wait_for(
                safe_record_conversation(
                    session_id=session_id,
                    tool_name=tool_id,
                    messages=messages,
                    response=response,
                ),
                timeout=settings.history.sync_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"[MEMORY] Synchronous store timeout after {settings.history.sync_timeout}s for {tool_id}"
            )
        except Exception as exc:
            logger.warning(f"[MEMORY] Synchronous store failed for {tool_id}: {exc}")
    else:
        # Background task (original behavior)
        logger.debug(f"[MEMORY] Creating background history storage task for {tool_id}")
        memory_task = asyncio.create_task(
            safe_record_conversation(
                session_id=session_id,
                tool_name=tool_id,
                messages=messages,
                response=response,
            )
        )
        memory_tasks.append(memory_task)


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
        self.capability_validator = CapabilityValidator()
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

        # Debug logging for structured output issue
        logger.debug(
            f"[EXECUTOR_DEBUG] execute() called with metadata.id={metadata.id}"
        )
        logger.debug(f"[EXECUTOR_DEBUG] kwargs keys: {list(kwargs.keys())}")
        logger.debug(
            f"[EXECUTOR_DEBUG] structured_output_schema in kwargs: {'structured_output_schema' in kwargs}"
        )
        if "structured_output_schema" in kwargs:
            logger.debug(
                f"[EXECUTOR_DEBUG] structured_output_schema value: {kwargs['structured_output_schema']}"
            )

        start_time = asyncio.get_event_loop().time()
        tool_id = metadata.id
        # Create unique operation ID early for consistent logging
        operation_id = f"{tool_id}_{uuid.uuid4().hex[:8]}"

        # Log request start with operation ID
        logger.info(f"[{operation_id}] Starting {tool_id}")

        vs_id: Optional[Union[str, Dict[str, Any]]] = (
            None  # Initialize to avoid UnboundLocalError
        )
        memory_tasks: List[asyncio.Task] = []  # Track history storage tasks
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

            # 3. Build optimized prompt using TokenBudgetOptimizer
            prompt_params = routed_params["prompt"]
            assert isinstance(prompt_params, dict)  # Type hint for mypy

            # Extract disable_history_record from adapter params
            adapter_params_check = routed_params.get("adapter", {})
            disable_history_record = False
            if isinstance(adapter_params_check, dict):
                disable_history_record = adapter_params_check.get(
                    "disable_history_record", False
                )

            # Get session info
            session_params = routed_params["session"]
            assert isinstance(session_params, dict)  # Type hint for mypy
            session_id = session_params.get("session_id")

            # Load settings and model configuration
            settings = get_settings()
            model_name = metadata.model_config["model_name"]
            model_limit = metadata.model_config.get("context_window", 128_000)

            # Load developer prompt for session history and optimization
            from ..prompts import get_developer_prompt

            developer_prompt = get_developer_prompt(model_name)

            # Extract context paths
            context_paths = prompt_params.get("context", [])
            priority_context_paths = prompt_params.get("priority_context", [])
            logger.info(f"[EXECUTOR] Extracted context_paths: {context_paths}")
            logger.info(
                f"[EXECUTOR] Extracted priority_context_paths: {priority_context_paths}"
            )
            instructions = prompt_params.get("instructions", "")
            output_format = prompt_params.get("output_format", "")

            # Get project name and tool name for all code paths
            import os

            project_path = settings.logging.project_path
            project_name = (
                os.path.basename(project_path)
                if project_path
                else os.path.basename(os.getcwd())
            )
            tool_name = metadata.id

            # Use TokenBudgetOptimizer for all prompt building
            if session_id:
                from ..optimization.token_budget_optimizer import TokenBudgetOptimizer

                # Fixed reserve for response generation and system overhead
                FIXED_TOKEN_RESERVE = 30_000

                optimizer = TokenBudgetOptimizer(
                    model_limit=model_limit,
                    fixed_reserve=FIXED_TOKEN_RESERVE,
                    session_id=session_id,
                    context_paths=context_paths,
                    priority_paths=priority_context_paths,
                    developer_prompt=developer_prompt,
                    instructions=instructions,
                    output_format=output_format,
                    project_name=project_name,
                    tool_name=tool_name,
                )

                try:
                    plan = await optimizer.optimize()
                    logger.info(
                        f"[EXECUTOR] Optimization complete: {plan.total_prompt_tokens:,} tokens "
                        f"in {plan.iterations} iterations"
                    )

                    # Use the optimized prompt and messages from the plan
                    final_prompt = plan.optimized_prompt
                    files_for_vector_store = plan.overflow_paths
                    messages = (
                        plan.messages
                    )  # Complete message list with session history

                except Exception as e:
                    logger.error(f"[EXECUTOR] Token budget optimization failed: {e}")
                    # Minimal fallback - use instructions/output format only
                    final_prompt = f"<instructions>\n{instructions}\n</instructions>\n\n<output_format>\n{output_format}\n</output_format>"

                    # Fallback: gather individual files from context directories for vector store
                    try:
                        from ..utils.fs import gather_file_paths_async

                        individual_files = await gather_file_paths_async(context_paths)
                        files_for_vector_store = individual_files
                        logger.debug(
                            f"[EXECUTOR] Fallback gathered {len(individual_files)} files for vector store"
                        )
                    except Exception as fs_error:
                        logger.warning(
                            f"[EXECUTOR] Could not gather files for fallback: {fs_error}"
                        )
                        files_for_vector_store = (
                            context_paths  # Last resort: use directories
                        )

                    # Build fallback messages without session history to avoid overflow
                    messages = [
                        {"role": "developer", "content": developer_prompt},
                        {"role": "user", "content": final_prompt},
                    ]
            else:
                # Fallback for sessions without ID - use legacy prompt engine
                final_prompt = await self.prompt_engine.build(
                    spec_class=metadata.spec_class,
                    prompt_params=prompt_params,
                )
                files_for_vector_store = []  # No optimization without session ID

                # Build messages for legacy prompt engine (no session optimization)
                messages = [
                    {"role": "developer", "content": developer_prompt},
                    {"role": "user", "content": final_prompt},
                ]

            # Store messages for conversation memory
            prompt_params["messages"] = messages
            # 4. Prepare vector store data for later creation
            vs_id = None
            vector_store_ids = None
            vector_store_files = None  # Store files for later creation
            vector_store_session_id = None  # Store session_id for later creation

            if session_id and files_for_vector_store:
                # Store for later creation after adapter instantiation
                vector_store_files = files_for_vector_store
                vector_store_session_id = session_id
                logger.debug(
                    f"Will create vector store with {len(files_for_vector_store)} overflow/attachment files after adapter instantiation"
                )
            else:
                # Fallback: Gather files from vector_store parameter if no session_id
                vector_store_param = routed_params.get("vector_store", [])
                assert isinstance(vector_store_param, list)  # Type hint for mypy
                if vector_store_param:
                    # Gather files from directories (skip safety check for attachments)
                    from ..utils.fs import gather_file_paths

                    files = gather_file_paths(
                        vector_store_param, skip_safety_check=True
                    )
                    logger.debug(
                        f"Gathered {len(files)} files from attachments: {files}"
                    )
                    if files:
                        # Store for later creation after adapter instantiation
                        vector_store_files = files
                        vector_store_session_id = None
                        logger.debug(
                            f"Will create vector store with {len(files)} attachment files after adapter instantiation"
                        )

            # Memory stores are no longer auto-attached
            # Models should use search_project_history function to access memory

            # 5. Check if this is a local service or an AI adapter
            service_cls = metadata.model_config.get("service_cls")

            if service_cls:
                # This is a local utility service
                logger.debug(f"[DEBUG] Using local service: {service_cls}")
                # Service class is already the actual class, not a string
                service = service_cls()

                # For local services, still do full parameter validation
                # but skip capability checks (pass None for capabilities)
                logger.debug(
                    "[STEP 1.5] Validating parameters for local tool (no capability checks)"
                )
                self.capability_validator.validate_against_capabilities(
                    metadata, validated_params, None
                )

                # For local services, we skip adapter-specific logic
                # and jump straight to execution
                adapter_params = routed_params["adapter"]
                assert isinstance(adapter_params, dict)

                # Add any prompt parameters that might be needed
                prompt_params_raw = routed_params.get("prompt", {})
                if isinstance(prompt_params_raw, dict):
                    prompt_params_for_service = {
                        k: v for k, v in prompt_params_raw.items() if k != "prompt"
                    }
                    adapter_params.update(prompt_params_for_service)

                # Execute the service
                result = await service.execute(**adapter_params)
                # Convert dict/list results to JSON for MCP compatibility
                if isinstance(result, (dict, list)):
                    import json

                    return json.dumps(result)
                return str(result)

            # Otherwise, get AI adapter from registry
            logger.debug("[DEBUG] About to get settings")
            settings = get_settings()
            logger.debug("[DEBUG] About to get adapter")

            # Get adapter class from registry and instantiate
            try:
                adapter_class_name = metadata.model_config["adapter_class"]
                model_name = metadata.model_config["model_name"]

                # Get adapter class from registry
                adapter_cls = get_adapter_class(adapter_class_name)

                # Instantiate adapter with model name
                adapter = adapter_cls(model_name)
                logger.debug(f"[DEBUG] Got adapter: {adapter}")

                # Validate parameters against adapter capabilities
                if hasattr(adapter, "capabilities"):
                    logger.debug(
                        f"[STEP 1.5] Validating parameters against {model_name} capabilities"
                    )
                    self.capability_validator.validate_against_capabilities(
                        metadata, validated_params, adapter.capabilities
                    )
                else:
                    logger.debug(
                        f"[STEP 1.5] Adapter {adapter_class_name} has no capabilities attribute, skipping capability validation"
                    )

            except KeyError:
                raise fastmcp.exceptions.ToolError(
                    f"Unknown adapter: {adapter_class_name}"
                )
            except Exception as e:
                raise fastmcp.exceptions.ToolError(f"Failed to initialize adapter: {e}")

            # 4.5. Now create vector store with adapter capabilities
            if vector_store_files:
                # Determine provider based on adapter capabilities
                provider_override = None
                if hasattr(adapter, "capabilities") and hasattr(
                    adapter.capabilities, "native_vector_store_provider"
                ):
                    provider_override = (
                        adapter.capabilities.native_vector_store_provider
                    )
                    if provider_override:
                        logger.info(
                            f"Using native vector store provider '{provider_override}' for {model_name}"
                        )
                else:
                    # If no native provider and default is openai, use hnsw for non-OpenAI adapters
                    # to avoid file type restrictions
                    adapter_class_name = adapter.__class__.__module__.split(".")[
                        -2
                    ]  # e.g., 'openai', 'google', 'xai'
                    if (
                        settings.mcp.default_vector_store_provider == "openai"
                        and adapter_class_name != "openai"
                    ):
                        provider_override = "hnsw"
                        logger.info(
                            f"Using 'hnsw' for {model_name} to avoid OpenAI file type restrictions"
                        )

                # Clear attachment search cache for new attachments
                from .search_task_files import SearchTaskFilesAdapter

                await SearchTaskFilesAdapter.clear_deduplication_cache()
                logger.debug(
                    "Cleared SearchTaskFilesAdapter deduplication cache for new task files"
                )

                logger.debug(
                    f"Creating vector store with {len(vector_store_files)} files using provider: {provider_override or 'default'}"
                )
                vs_result = await self.vector_store_manager.create(
                    vector_store_files,
                    session_id=vector_store_session_id,
                    provider=provider_override,
                )
                vs_id = (
                    vs_result.get("store_id") if isinstance(vs_result, dict) else None
                )
                vector_store_ids = [vs_id] if vs_id else None
                logger.debug(
                    f"Vector store ready: {vs_id}, vector_store_ids={vector_store_ids}"
                )

                # E2E verbose logging - log vector store details when DEBUG is enabled
                if logger.isEnabledFor(logging.DEBUG) and vs_id:
                    logger.debug(
                        f"[{operation_id}] Created vector store {vs_id} with {len(vector_store_files)} files for session {vector_store_session_id or 'attachments'}"
                    )

            # 6. Handle session - unified for all adapters
            session_params = routed_params["session"]
            assert isinstance(session_params, dict)  # Type hint for mypy
            session_id = session_params.get("session_id")

            # All adapters now handle sessions uniformly via unified session cache
            # The adapters themselves will load/save session history as needed
            if session_id:
                logger.debug(f"Session {session_id} will be handled by adapter")

            # 7. Create parameters for MCPAdapter protocol
            logger.debug(
                "[STEP 14] Preparing adapter parameters for MCPAdapter protocol"
            )

            # Import SimpleNamespace for creating the params instance
            from types import SimpleNamespace

            # Consolidate all routed parameters into one dictionary
            param_data = {}

            # Add adapter-specific parameters
            adapter_params = routed_params["adapter"]
            assert isinstance(adapter_params, dict)
            logger.debug(
                f"[PARAM_DEBUG] adapter_params keys: {list(adapter_params.keys())}"
            )
            param_data.update(adapter_params)

            # Add session parameters
            session_params = routed_params.get("session", {})
            param_data.update(session_params)

            # Add structured output parameters (only if model supports them)
            structured_output_params = routed_params.get("structured_output", {})

            # Check if model supports structured output before adding these parameters
            if metadata.capabilities and hasattr(
                metadata.capabilities, "supports_structured_output"
            ):
                if metadata.capabilities.supports_structured_output:
                    param_data.update(structured_output_params)

                    # Handle structured output schema parsing
                    schema_str = None
                    if isinstance(structured_output_params, dict):
                        schema_str = structured_output_params.get(
                            "structured_output_schema"
                        )
                    if schema_str is not None:
                        try:
                            import json

                            schema = (
                                json.loads(schema_str)
                                if isinstance(schema_str, str)
                                else schema_str
                            )
                            param_data["structured_output_schema"] = schema
                        except (json.JSONDecodeError, ValueError) as e:
                            raise ValueError(
                                f"Invalid JSON in structured_output_schema: {e}"
                            )
                else:
                    logger.debug(
                        f"Skipping structured output parameters for {metadata.id} - not supported by model"
                    )
            else:
                # For local tools or models without capabilities, skip structured output
                logger.debug(
                    f"Skipping structured output parameters for {metadata.id} - no capabilities defined"
                )

            # Add prompt parameters that adapters might need
            # Instructions and output_format are used to build the XML prompt
            # Context is handled separately for file gathering
            prompt_params_for_adapter = {
                k: v
                for k, v in prompt_params.items()
                if k
                not in [
                    "prompt",
                    "messages",
                    "context",
                    "instructions",
                    "output_format",
                ]
            }
            logger.debug(
                f"[PARAM_DEBUG] prompt_params_for_adapter keys: {list(prompt_params_for_adapter.keys())}"
            )
            param_data.update(prompt_params_for_adapter)

            # Add defaults from the adapter's param class for any missing parameters
            # This ensures all expected attributes exist on the SimpleNamespace
            if hasattr(adapter, "param_class"):
                param_class = adapter.param_class
                # Import the sentinel value to check for no default
                from ..tools.descriptors import _NO_DEFAULT

                # Get all Route descriptors from the param class
                for attr_name in dir(param_class):
                    if attr_name.startswith("_"):
                        continue
                    attr_value = getattr(param_class, attr_name)
                    # Check if it's a RouteDescriptor
                    if hasattr(attr_value, "route") and hasattr(attr_value, "default"):
                        # Add the default value if not already provided
                        if attr_name not in param_data:
                            # Check if this parameter has capability requirements
                            if (
                                hasattr(attr_value, "requires_capability")
                                and attr_value.requires_capability
                            ):
                                # Validate capability before adding default
                                capabilities = getattr(adapter, "capabilities", None)
                                if capabilities:
                                    try:
                                        if not attr_value.requires_capability(
                                            capabilities
                                        ):
                                            # Skip this parameter - not supported by model
                                            logger.debug(
                                                f"[PARAM_DEBUG] Skipping default for {attr_name} - not supported by model"
                                            )
                                            continue
                                    except Exception:
                                        # If capability check fails, skip the parameter
                                        logger.debug(
                                            f"[PARAM_DEBUG] Capability check failed for {attr_name}, skipping"
                                        )
                                        continue

                            # Handle default_factory
                            if attr_value.default_factory is not None:
                                default_val = attr_value.default_factory()
                            elif attr_value.default is not _NO_DEFAULT:
                                default_val = attr_value.default
                            else:
                                # No default specified, skip
                                continue
                            param_data[attr_name] = default_val
                            logger.debug(
                                f"[PARAM_DEBUG] Added default for {attr_name}: {default_val}"
                            )

            # Create the params instance using SimpleNamespace
            logger.debug(
                f"[PARAM_DEBUG] Final param_data keys: {list(param_data.keys())}"
            )
            logger.debug(f"[PARAM_DEBUG] param_data: {param_data}")

            # ALWAYS ensure structured_output_schema exists for compatibility
            # Set to None for models that don't support it
            if "structured_output_schema" not in param_data:
                param_data["structured_output_schema"] = None
                logger.debug(
                    "[PARAM_DEBUG] Added structured_output_schema=None for compatibility"
                )

            logger.debug(
                f"[PARAM_DEBUG] Final structured_output_schema: {param_data.get('structured_output_schema')}"
            )

            params_instance = SimpleNamespace(**param_data)

            # Create CallContext
            from ..adapters.protocol import CallContext

            explicit_vs_ids = routed_params.get("vector_store_ids", [])
            assert isinstance(explicit_vs_ids, list)
            if explicit_vs_ids:
                vector_store_ids = (vector_store_ids or []) + list(explicit_vs_ids)

            call_context = CallContext(
                session_id=session_id or "",
                project=project_name,
                tool=tool_name,
                vector_store_ids=vector_store_ids,
            )

            # Create ToolDispatcher
            from ..adapters.tool_dispatcher import (
                ToolDispatcher as ProtocolToolDispatcher,
            )

            tool_dispatcher = ProtocolToolDispatcher(vector_store_ids=vector_store_ids)

            timeout_seconds = metadata.model_config["timeout"]
            adapter_start_time = time.time()
            logger.debug(
                f"[STEP 15] Calling adapter.generate with MCPAdapter protocol, prompt {len(final_prompt)} chars, timeout={timeout_seconds}s"
            )
            logger.debug(
                f"[TIMING] Starting adapter.generate at {time.strftime('%H:%M:%S')}"
            )

            # Renew lease before long-running operation
            if session_id and vs_id:
                await self.vector_store_manager.renew_lease(session_id)
                logger.debug(f"Renewed vector store lease for session {session_id}")

            # Scope context is now set by the integration layer, so we don't need to set it here
            try:
                # Call adapter.generate with MCPAdapter protocol signature
                # Build kwargs for generate call
                generate_kwargs = {
                    "timeout": timeout_seconds,
                    "vector_store_ids": vector_store_ids,  # Pass as kwarg for backward compat
                }

                # For Gemini models, pass system_instruction separately
                if adapter_class_name == "google":
                    generate_kwargs["system_instruction"] = developer_prompt
                    # Pass a copy to prevent mutations from affecting history storage
                    generate_kwargs["messages"] = messages.copy()
                elif adapter_class_name in ["openai", "xai"]:
                    # OpenAI and Grok models use messages with developer role
                    # Pass a copy to prevent mutations from affecting history storage
                    generate_kwargs["messages"] = messages.copy()

                # DEBUG: Log exact messages sent to API for token analysis
                debug_data = {
                    "session_id": session_id,
                    "final_prompt": final_prompt,
                    "messages": generate_kwargs.get("messages", []),
                    "developer_prompt": developer_prompt
                    if adapter_class_name == "google"
                    else None,
                    "adapter_class": adapter_class_name,
                    "estimated_tokens": getattr(plan, "total_prompt_tokens", "unknown")
                    if "plan" in locals()
                    else "no_plan",
                }

                # Debug JSON file saving removed to reduce clutter

                result = await operation_manager.run_with_timeout(
                    operation_id,
                    adapter.generate(
                        prompt=final_prompt,
                        params=params_instance,  # Pass the SimpleNamespace instance
                        ctx=call_context,
                        tool_dispatcher=tool_dispatcher,
                        **generate_kwargs,
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
                logger.debug(f"[CANCEL] Adapter was: {adapter}")
                logger.debug("[CANCEL] Re-raising CancelledError from executor")
                raise  # Important: do NOT convert or return
            except Exception as e:
                logger.error(
                    f"[{operation_id}] [CRITICAL] Adapter generate failed for {tool_id}: {e}"
                )
                raise

            # 8. Handle response
            logger.debug("[STEP 17] Handling response")

            # CRITICAL: Update sent file cache ONLY after successful API call
            if (
                session_id
                and "plan" in locals()
                and hasattr(plan, "sent_files_info")
                and plan.sent_files_info
            ):
                try:
                    from ..utils.stable_list_cache import StableListCache

                    cache = StableListCache()
                    await cache.batch_update_sent_files(
                        session_id, plan.sent_files_info
                    )
                    logger.debug(
                        f"[EXECUTOR] Updated sent file cache for {len(plan.sent_files_info)} files after successful API call"
                    )
                except Exception as e:
                    logger.warning(
                        f"[EXECUTOR] Failed to update sent file cache after success: {e}"
                    )

            if isinstance(result, dict):
                logger.debug("[STEP 17.1] Result is dict")
                content = result.get("content", "")
                logger.debug(f"[STEP 17.2] Got content, length: {len(str(content))}")
                # Session management is handled by adapters via the unified session cache
                # Each adapter decides what to store (response_id for OpenAI, full history for others)
                # Session management is now handled inside the adapters themselves
                # No need to save sessions here for Vertex/Grok models

                # Redact secrets from content
                logger.debug("[STEP 17.5] Starting redaction")
                # Skip redaction for MockAdapter responses to avoid regex timeout
                if adapter.__class__.__name__ == "MockAdapter":
                    redacted_content = str(content)
                else:
                    redacted_content = redact_secrets(str(content))
                logger.debug("[STEP 17.6] Redaction complete")

                # 8a. Store conversation in memory (with redacted content)
                try:
                    # Extract messages from prompt
                    conv_messages = prompt_params.get("messages", [])
                    if not isinstance(conv_messages, list):
                        conv_messages = []
                    # Re-enabled: Memory storage is important for context
                    await _maybe_store_memory(
                        session_id=session_id,
                        tool_id=tool_id,
                        messages=conv_messages,
                        response=redacted_content,
                        disable_history_record=disable_history_record,
                        memory_tasks=memory_tasks,
                    )
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
                try:
                    conv_messages = prompt_params.get("messages", [])
                    if not isinstance(conv_messages, list):
                        conv_messages = []
                    # Re-enabled: Memory storage is important for context
                    await _maybe_store_memory(
                        session_id=session_id,
                        tool_id=tool_id,
                        messages=conv_messages,
                        response=redacted_result,
                        disable_history_record=disable_history_record,
                        memory_tasks=memory_tasks,
                    )
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
                    f"[MEMORY] Cancelling {len(memory_tasks)} history storage tasks due to operation cancellation"
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

            # Don't wait for memory tasks - they're fire-and-forget
            # This was blocking the response for 8+ seconds while uploading to vector store
            # if memory_tasks:
            #     with contextlib.suppress(asyncio.TimeoutError):
            #         await asyncio.wait_for(
            #             asyncio.gather(*memory_tasks, return_exceptions=True),
            #             timeout=120.0,  # Original timeout for history storage
            #         )

            elapsed = asyncio.get_event_loop().time() - start_time
            logger.info(f"[{operation_id}] {tool_id} completed in {elapsed:.2f}s")


# Global executor instance
# Set strict_mode=True if you want to reject unknown parameters
executor = ToolExecutor(strict_mode=False)

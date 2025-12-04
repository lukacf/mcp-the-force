"""Base adapter for LiteLLM-based adapters with shared functionality."""

import logging
from typing import Any, Dict, List, Optional
from abc import abstractmethod
from contextvars import ContextVar

import litellm
from litellm import aresponses

from .protocol import CallContext, ToolDispatcher
from .capabilities import AdapterCapabilities
from .errors import ToolExecutionException
from ..unified_session_cache import UnifiedSessionCache

logger = logging.getLogger(__name__)

# Configure LiteLLM globally
litellm.set_verbose = False
litellm.drop_params = True  # Drop unknown parameters

# --- BEGIN: LiteLLM header propagation patch ---
# Context-scoped store for headers we want to guarantee reach acompletion
_LITELLM_EXTRA_HEADERS_CTX: ContextVar[dict | None] = ContextVar(
    "_LITELLM_EXTRA_HEADERS_CTX", default=None
)


def _ensure_litellm_header_patch() -> None:
    """
    Patch litellm.acompletion once so it always merges headers from our context.
    This works around aresponses dropping extra_headers when delegating to acompletion.
    """
    if getattr(litellm, "_mcp_header_patch_installed", False):
        return

    _orig_acompletion = litellm.acompletion  # keep reference

    async def _acompletion_with_ctx_headers(*args, **kwargs):
        ctx_headers = _LITELLM_EXTRA_HEADERS_CTX.get()
        req_headers = kwargs.get("extra_headers")

        # Merge: request-level wins over context-level on key conflicts
        if ctx_headers and req_headers:
            merged = {**ctx_headers, **req_headers}
            kwargs["extra_headers"] = merged
        elif ctx_headers and not req_headers:
            kwargs["extra_headers"] = ctx_headers
        # else: keep req_headers as-is (could be None)

        return await _orig_acompletion(*args, **kwargs)

    litellm.acompletion = _acompletion_with_ctx_headers  # type: ignore
    litellm._mcp_header_patch_installed = True


def _sanitize_conversation_input(conversation_input: List[Dict[str, Any]]) -> None:
    """
    Sanitize conversation_input to fix common issues that cause provider errors.

    Fixes:
    - Messages with content=None (causes "Invalid content type: NoneType" in Anthropic)
    - Messages with missing required fields
    - Items without content field (litellm bug: it calls .get("content") on ALL items)

    Mutates conversation_input in-place.
    """
    for msg in conversation_input:
        msg_type = msg.get("type")

        # CRITICAL WORKAROUND for litellm bug:
        # litellm's _transform_responses_api_input_item_to_chat_completion_message calls
        # input_item.get("content") on ALL items, including function_call and function_call_output.
        # When content is missing or None, it fails with "Invalid content type: NoneType".
        # We must ensure ALL items have a valid content field.
        if "content" not in msg or msg["content"] is None:
            # Set to empty text content array for Responses API format
            msg["content"] = [{"type": "text", "text": ""}]
            logger.debug(
                f"Sanitized item with missing/None content: type={msg_type}, role={msg.get('role')}"
            )

        # For message types with content, ensure content items are valid
        if msg_type == "message":
            content = msg.get("content")
            if isinstance(content, list):
                # Ensure all content items have valid structure
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text" and item.get("text") is None:
                            item["text"] = ""
                            logger.debug("Sanitized text content item with None text")

        # For function_call and function_call_output, ensure required fields exist
        elif msg_type == "function_call":
            if msg.get("arguments") is None:
                msg["arguments"] = "{}"
            # Gemini requires thought_signature on all function_call items
            # Use the special bypass signature if not present
            if not msg.get("thought_signature"):
                msg["thought_signature"] = "skip_thought_signature_validator"
                msg["thoughtSignature"] = "skip_thought_signature_validator"
        elif msg_type == "function_call_output":
            if msg.get("output") is None:
                msg["output"] = ""


def _dedup_tool_ids(conversation_input: List[Dict[str, Any]]) -> None:
    """
    Deduplicate tool/function IDs to satisfy providers (e.g., Anthropic) that require unique ids per request.
    Maintains call_id sync between function_call and function_call_output pairs.
    Handles overlapping calls (multiple calls with same ID before any outputs).
    Mutates conversation_input in-place.
    """
    from collections import defaultdict

    seen_call_ids: set[str] = set()  # All rewritten call_ids encountered
    seen_tool_use_ids: set[str] = set()
    pending_calls: dict[str, list[str]] = defaultdict(
        list
    )  # original_id -> queue of rewritten_ids
    tool_use_id_mapping: dict[str, str] = {}

    def get_unique_call_id(raw_id: Optional[str], msg_type: str) -> Optional[str]:
        """Map a call_id considering function_call/function_call_output pairing."""
        if not raw_id:
            return None

        if msg_type == "function_call":
            # Check if this is a duplicate (pending calls OR already seen before)
            if pending_calls[raw_id] or raw_id in seen_call_ids:
                # Duplicate - generate new unique ID
                i = 2
                new_id = f"{raw_id}-dup{i}"
                while new_id in seen_call_ids:
                    i += 1
                    new_id = f"{raw_id}-dup{i}"
                seen_call_ids.add(new_id)
                pending_calls[raw_id].append(new_id)  # Add to queue
                return new_id
            else:
                # First occurrence
                seen_call_ids.add(raw_id)
                pending_calls[raw_id].append(raw_id)  # Add to queue
                return raw_id

        elif msg_type == "function_call_output":
            # Pop the oldest pending call with this original ID (FIFO)
            if pending_calls[raw_id]:
                # Use the same (possibly renamed) ID as the call
                rewritten_id = pending_calls[raw_id].pop(0)  # Pop from front (FIFO)
                return rewritten_id
            else:
                # Orphaned output without a preceding call
                if raw_id not in seen_call_ids:
                    seen_call_ids.add(raw_id)
                    return raw_id
                i = 2
                new_id = f"{raw_id}-dup{i}"
                while new_id in seen_call_ids:
                    i += 1
                    new_id = f"{raw_id}-dup{i}"
                seen_call_ids.add(new_id)
                return new_id

        return None

    def get_unique_tool_use_id(raw_id: Optional[str]) -> Optional[str]:
        """Map a tool_use ID to a unique value."""
        if not raw_id:
            return None

        if raw_id in tool_use_id_mapping:
            return tool_use_id_mapping[raw_id]

        if raw_id not in seen_tool_use_ids:
            seen_tool_use_ids.add(raw_id)
            tool_use_id_mapping[raw_id] = raw_id
            return raw_id

        i = 2
        new_id = f"{raw_id}-dup{i}"
        while new_id in seen_tool_use_ids:
            i += 1
            new_id = f"{raw_id}-dup{i}"
        seen_tool_use_ids.add(new_id)
        tool_use_id_mapping[raw_id] = new_id
        return new_id

    for msg in conversation_input:
        # Responses API function calls / outputs
        msg_type = msg.get("type")
        if msg_type in {"function_call", "function_call_output"}:
            cid = msg.get("call_id")
            new_cid = get_unique_call_id(cid, msg_type)
            if new_cid and new_cid != cid:
                msg["call_id"] = new_cid

        # Anthropic-style tool_use blocks may be nested inside content
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    tid = part.get("id")
                    new_tid = get_unique_tool_use_id(tid)
                    if new_tid and new_tid != tid:
                        part["id"] = new_tid


def _update_litellm_model_limits() -> None:
    """
    Update LiteLLM's internal model cost table to reflect 1M context for Claude 4 Sonnet.
    This prevents the preflight validation from rejecting large inputs before they're sent.
    """
    if getattr(litellm, "_mcp_model_limits_patched", False):
        return

    try:
        # Access LiteLLM's model cost table
        model_cost = getattr(litellm, "model_cost", {})

        # Keys to update for Claude 4 Sonnet 1M context
        sonnet_keys = ["claude-sonnet-4-20250514", "anthropic/claude-sonnet-4-20250514"]

        for key in sonnet_keys:
            if key in model_cost:
                # Update max_input_tokens to 1M while preserving other fields
                model_info = model_cost[key]
                old_limit = model_info.get("max_input_tokens", "unknown")
                model_info["max_input_tokens"] = 1_000_000
                logger.debug(
                    f"Updated {key} max_input_tokens: {old_limit} -> 1,000,000"
                )

        litellm._mcp_model_limits_patched = True

    except Exception as e:
        logger.warning(f"Failed to update LiteLLM model limits: {e}")
        logger.warning(
            "Large context requests may still be blocked by LiteLLM's preflight validation"
        )


# --- END: LiteLLM header propagation patch ---


class LiteLLMBaseAdapter:
    """Base class for LiteLLM-based adapters.

    This provides common functionality for adapters that use LiteLLM's
    Responses API, including session management, tool handling, and
    response formatting.
    """

    # Protocol requirements - subclasses must set these
    model_name: str
    display_name: str
    capabilities: AdapterCapabilities
    param_class: type

    def __init__(self):
        """Initialize base adapter.

        Subclasses should call super().__init__() after setting their
        model_name, display_name, capabilities, and param_class.
        """
        _ensure_litellm_header_patch()
        _update_litellm_model_limits()
        self._validate_environment()

    @abstractmethod
    def _validate_environment(self):
        """Validate environment configuration.

        Subclasses must implement this to check for required API keys
        or environment variables.
        """
        pass

    @abstractmethod
    def _get_model_prefix(self) -> str:
        """Get the LiteLLM model prefix for this provider.

        Returns:
            The provider prefix (e.g., "vertex_ai", "xai")
        """
        pass

    async def _load_session_history(
        self, project: str, tool: str, session_id: str
    ) -> List[Dict[str, Any]]:
        """Load session history from cache.

        Args:
            project: Project identifier
            tool: Tool identifier
            session_id: Session identifier

        Returns:
            Conversation history in Responses API format
        """
        history = await UnifiedSessionCache.get_history(project, tool, session_id)
        if history:
            logger.debug(
                f"[{self.display_name}] Loaded {len(history)} items from session {session_id}"
            )
            return history
        return []

    def _build_conversation_input(
        self,
        prompt: str,
        ctx: CallContext,
        system_instruction: Optional[str] = None,
        structured_output_schema: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build conversation input for the current turn.

        Args:
            prompt: User prompt
            ctx: Call context
            system_instruction: Optional system instruction
            structured_output_schema: Optional JSON schema

        Returns:
            Conversation input in Responses API format
        """
        conversation_input = []

        # Handle system instruction
        if system_instruction:
            conversation_input.append(
                {
                    "type": "message",
                    "role": "system",
                    "content": [{"type": "text", "text": system_instruction}],
                }
            )

        # Add JSON formatting instruction if needed
        prompt_text = prompt
        if structured_output_schema:
            import json as _json

            schema_text = (
                structured_output_schema
                if isinstance(structured_output_schema, str)
                else _json.dumps(structured_output_schema, separators=(",", ":"))
            )
            prompt_text = f"{prompt}\n\nRespond ONLY with valid JSON that matches this schema: {schema_text}"

        # Add user message
        conversation_input.append(
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "text", "text": prompt_text}],
            }
        )

        return conversation_input

    def _get_tool_declarations(
        self,
        tool_dispatcher: Optional[ToolDispatcher],
        disable_history_search: bool = False,
        additional_tools: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Get all tool declarations.

        Args:
            tool_dispatcher: Tool dispatcher instance
            disable_history_search: Whether to disable memory search
            additional_tools: Additional tools to include

        Returns:
            List of tool declarations
        """
        tools = []

        if tool_dispatcher:
            built_in_tools = tool_dispatcher.get_tool_declarations(
                capabilities=self.capabilities,
                disable_history_search=disable_history_search,
            )
            tools.extend(built_in_tools)

        if additional_tools:
            tools.extend(additional_tools)

        return tools

    @abstractmethod
    def _build_request_params(
        self,
        conversation_input: List[Dict[str, Any]],
        params: Any,
        tools: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Build provider-specific request parameters.

        Args:
            conversation_input: Conversation in Responses API format
            params: Tool-specific parameters
            tools: Tool declarations
            **kwargs: Additional parameters

        Returns:
            Request parameters for LiteLLM
        """
        pass

    async def _handle_tool_calls(
        self,
        response: Any,
        tool_dispatcher: ToolDispatcher,
        conversation_input: List[Dict[str, Any]],
        request_params: Dict[str, Any],
        ctx: CallContext,
    ) -> tuple[Any, List[Dict[str, Any]]]:
        """Handle tool calls in the response.

        Args:
            response: LiteLLM response
            tool_dispatcher: Tool dispatcher
            conversation_input: Current conversation
            request_params: Request parameters

        Returns:
            Tuple of (final_response, updated_conversation)
        """
        final_response = response
        updated_conversation = list(conversation_input)

        # Handle tool calls in Responses API format
        while True:
            # Extract content and tool calls from response.output
            tool_calls = []
            final_content = ""

            if hasattr(response, "output"):
                for item in response.output:
                    if item.type == "message" and hasattr(item, "content"):
                        if isinstance(item.content, str):
                            final_content = item.content
                        elif isinstance(item.content, list):
                            for content_item in item.content:
                                if hasattr(content_item, "text"):
                                    final_content = content_item.text
                    elif item.type == "function_call":
                        tool_calls.append(item)

            # If no tool calls, we're done
            if not tool_calls:
                break

            logger.debug(f"Processing {len(tool_calls)} tool calls")

            # Add assistant message to conversation
            updated_conversation.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": final_content or ""}],
                }
            )

            # Execute tool calls
            for tool_call in tool_calls:
                logger.debug(
                    f"Executing tool: {tool_call.name} raw={getattr(tool_call, '__dict__', {})}"
                )
                # Preserve the function_call record (including thought_signature for Gemini)
                fc_msg = {
                    "type": "function_call",
                    "name": getattr(tool_call, "name", None),
                    "arguments": getattr(tool_call, "arguments", None),
                    "call_id": getattr(tool_call, "call_id", None),
                }
                thought_sig = getattr(tool_call, "thought_signature", None)
                if not thought_sig and hasattr(tool_call, "provider_specific_fields"):
                    thought_sig = getattr(
                        tool_call, "provider_specific_fields", {}
                    ).get("thought_signature")
                logger.debug(
                    f"[TOOL_CALL] name={getattr(tool_call, 'name', None)} "
                    f"call_id={getattr(tool_call, 'call_id', None)} "
                    f"has_thought_sig={bool(thought_sig)} "
                    f"provider_fields={getattr(tool_call, 'provider_specific_fields', None)}"
                )
                if not thought_sig:
                    # Use Gemini's special validator-skip signature when no real signature is available
                    # See: https://ai.google.dev/gemini-api/docs/thought-signatures
                    thought_sig = "skip_thought_signature_validator"
                fc_msg["thought_signature"] = thought_sig
                fc_msg["thoughtSignature"] = thought_sig  # some SDKs expect camelCase
                # Gemini expects the signature nested under functionCall
                try:
                    import json as _json

                    parsed_args = getattr(tool_call, "arguments", None)
                    if isinstance(parsed_args, str):
                        try:
                            parsed_args = _json.loads(parsed_args)
                        except Exception:
                            parsed_args = parsed_args
                    fc_msg["functionCall"] = {
                        "name": getattr(tool_call, "name", None),
                        "args": parsed_args,
                        "thoughtSignature": thought_sig,
                    }
                except Exception:
                    pass  # non-fatal; best-effort enrichment
                updated_conversation.append(fc_msg)

                try:
                    result = await tool_dispatcher.execute(
                        tool_name=tool_call.name,
                        tool_args=tool_call.arguments,
                        context=ctx,
                    )
                    updated_conversation.append(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": str(result),
                        }
                    )
                except Exception as e:
                    tool_error = ToolExecutionException(
                        tool_name=tool_call.name, error=e, provider=self.display_name
                    )
                    logger.error(str(tool_error))
                    updated_conversation.append(
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": f"Error: {str(e)}",
                        }
                    )

            # Continue conversation with tool results
            logger.warning(
                f"[{self.display_name}] TOOL LOOP BEFORE SANITIZE: {len(updated_conversation)} items"
            )
            for idx, item in enumerate(updated_conversation):
                if "content" in item and item["content"] is None:
                    logger.error(
                        f"[{self.display_name}] TOOL LOOP PRE-SANITIZE content=None at {idx}: {item}"
                    )
            _sanitize_conversation_input(updated_conversation)
            logger.warning(
                f"[{self.display_name}] TOOL LOOP AFTER SANITIZE: {len(updated_conversation)} items"
            )
            for idx, item in enumerate(updated_conversation):
                item_type = item.get("type", "NO_TYPE")
                item_content = item.get("content")
                content_type = type(item_content).__name__
                logger.warning(
                    f"[{self.display_name}] TOOL_LOOP_INPUT[{idx}]: type={item_type}, "
                    f"content_type={content_type}, has_content={'content' in item}"
                )
                if "content" in item and item["content"] is None:
                    logger.error(
                        f"[{self.display_name}] TOOL LOOP POST-SANITIZE content=None at {idx}: {item}"
                    )
            request_params["input"] = updated_conversation
            response = await aresponses(**request_params)
            final_response = response

        return final_response, updated_conversation

    async def _save_session(
        self,
        ctx: CallContext,
        conversation_input: List[Dict[str, Any]],
        response: Any,
        updated_conversation: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Save session state.

        Args:
            ctx: Call context
            conversation_input: Original conversation
            response: Final response
            updated_conversation: Updated conversation with tool calls
        """
        if ctx.session_id:
            # Use updated conversation if available (includes tool calls)
            final_conversation = updated_conversation or conversation_input

            # Extract final content and add assistant response if not already included
            final_content = self._extract_content(response)
            if final_content and (
                not final_conversation
                or final_conversation[-1].get("role") != "assistant"
            ):
                assistant_msg = {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": final_content}],
                }
                final_conversation.append(assistant_msg)

            # Save to cache
            await UnifiedSessionCache.set_history(
                ctx.project,
                ctx.tool,
                ctx.session_id,
                final_conversation,
            )

    def _extract_content(self, response: Any) -> str:
        """Extract content from LiteLLM Responses API response.

        Args:
            response: LiteLLM response object

        Returns:
            Extracted content string
        """
        final_content = ""

        if hasattr(response, "output"):
            for item in response.output:
                if item.type == "message" and hasattr(item, "content"):
                    if isinstance(item.content, str):
                        final_content = item.content
                    elif isinstance(item.content, list):
                        for content_item in item.content:
                            if hasattr(content_item, "text"):
                                final_content = content_item.text

        return final_content

    async def generate(
        self,
        prompt: str,
        params: Any,
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate response using LiteLLM.

        This is the main method that subclasses typically won't need to override.
        Instead, they should implement the abstract methods.

        Args:
            prompt: User prompt
            params: Tool-specific parameters
            ctx: Call context
            tool_dispatcher: Tool dispatcher
            **kwargs: Additional parameters

        Returns:
            Dict with "content" and other response data
        """
        token = None
        try:
            # Load session history if needed
            conversation_input = []
            if ctx.session_id:
                conversation_input = await self._load_session_history(
                    ctx.project, ctx.tool, ctx.session_id
                )

            # Build conversation for current turn
            conversation_input.extend(
                self._build_conversation_input(
                    prompt,
                    ctx,
                    system_instruction=kwargs.get("system_instruction"),
                    structured_output_schema=getattr(
                        params, "structured_output_schema", None
                    ),
                )
            )

            # Sanitize and deduplicate conversation input to satisfy providers (e.g., Anthropic)
            logger.warning(
                f"[{self.display_name}] BEFORE SANITIZE: {len(conversation_input)} items"
            )
            for idx, item in enumerate(conversation_input):
                if "content" in item and item["content"] is None:
                    logger.error(
                        f"[{self.display_name}] PRE-SANITIZE content=None at {idx}: {item}"
                    )
            _sanitize_conversation_input(conversation_input)
            logger.warning(
                f"[{self.display_name}] AFTER SANITIZE: {len(conversation_input)} items"
            )
            for idx, item in enumerate(conversation_input):
                if "content" in item and item["content"] is None:
                    logger.error(
                        f"[{self.display_name}] POST-SANITIZE content=None at {idx}: {item}"
                    )
            _dedup_tool_ids(conversation_input)

            # Get tool declarations
            disable_history_search_value = getattr(
                params, "disable_history_search", False
            )
            logger.debug(
                f"[LITELLM_BASE] params.disable_history_search = {disable_history_search_value}"
            )
            tools = self._get_tool_declarations(
                tool_dispatcher,
                disable_history_search=disable_history_search_value,
                additional_tools=kwargs.get("tools"),
            )

            # Build provider-specific request parameters
            request_params = self._build_request_params(
                conversation_input, params, tools, **kwargs
            )

            # Debug logging for request parameters
            import json as _json

            input_data = request_params.get("input", [])
            input_size = len(_json.dumps(input_data, default=str))
            tools_count = len(request_params.get("tools", []))
            logger.info(
                f"[{self.display_name}] LiteLLM request: model={request_params.get('model')}, "
                f"has_api_key={bool(request_params.get('api_key'))}, "
                f"vertex_project={request_params.get('vertex_project')}, "
                f"vertex_location={request_params.get('vertex_location')}, "
                f"input_size={input_size:,} bytes, tools_count={tools_count}"
            )

            # DEBUG: Log each input item to find content=None issue
            for idx, item in enumerate(input_data):
                item_type = item.get("type", "NO_TYPE")
                item_role = item.get("role", "NO_ROLE")
                item_content = item.get("content")
                content_type = type(item_content).__name__
                logger.warning(
                    f"[{self.display_name}] INPUT[{idx}]: type={item_type}, role={item_role}, "
                    f"content_type={content_type}, has_content={'content' in item}"
                )
                if item_content is None and "content" in item:
                    logger.error(
                        f"[{self.display_name}] FOUND content=None at index {idx}: {item}"
                    )

            # Ensure headers propagate to acompletion even if aresponses drops them
            token = _LITELLM_EXTRA_HEADERS_CTX.set(request_params.get("extra_headers"))

            # Make the API call with explicit timeout
            import time as _time

            # Use a 5 minute timeout - should be plenty for any reasonable API call
            # (curl returns in ~20s for the same request)
            request_params["timeout"] = 300

            _api_start = _time.monotonic()
            response = await aresponses(**request_params)
            _api_elapsed = _time.monotonic() - _api_start
            logger.info(
                f"[{self.display_name}] LiteLLM API call completed in {_api_elapsed:.2f}s"
            )

            # Handle tool calls if present (still under the same context headers)
            final_response, updated_conversation = await self._handle_tool_calls(
                response, tool_dispatcher, conversation_input, request_params, ctx
            )

            # Save session state
            await self._save_session(
                ctx, conversation_input, final_response, updated_conversation
            )

            # Extract and return content
            content = self._extract_content(final_response)
            result = {"content": content}

            # Add any provider-specific response data
            if hasattr(self, "_add_provider_specific_data"):
                result.update(self._add_provider_specific_data(final_response, params))

            return result

        except Exception as e:
            logger.error(f"[{self.display_name}] Error: {e}")
            raise
        finally:
            # Clean up the context var to avoid leaking to other tasks
            if token is not None:
                try:
                    _LITELLM_EXTRA_HEADERS_CTX.reset(token)
                except Exception:
                    pass

"""Format converters between Responses API and google-genai native format.

This module handles conversion between:
- Responses API format (used in UnifiedSessionCache)
- google-genai SDK native format (Content, Part, etc.)

The Responses API format is our internal representation:
[
    {"type": "message", "role": "user", "content": [{"type": "text", "text": "..."}]},
    {"type": "function_call", "name": "...", "call_id": "...", "arguments": "...", "thought_signature": "..."},
    {"type": "function_call_output", "call_id": "...", "output": "..."},
]

The google-genai format uses Content and Part objects:
[
    Content(role="user", parts=[Part(text="...")]),
    Content(role="model", parts=[Part(function_call=FunctionCall(...), thought_signature=b"...")]),
    Content(role="user", parts=[Part(function_response=FunctionResponse(...))]),
]
"""

import json
import logging
from typing import Any, Dict, List, Optional

from google.genai import types

logger = logging.getLogger(__name__)


def responses_to_contents(history: List[Dict[str, Any]]) -> List[types.Content]:
    """Convert Responses API history to google-genai Content list.

    Handles:
    - "message" type → Content with text Part(s)
    - "function_call" type → Content(role="model") with Part containing FunctionCall
    - "function_call_output" type → Content(role="user") with Part containing FunctionResponse

    Consecutive function_calls are grouped into a single model Content.
    Consecutive function_call_outputs are grouped into a single user Content.

    Args:
        history: List of Responses API format messages

    Returns:
        List of google-genai Content objects
    """
    if not history:
        return []

    contents: List[types.Content] = []
    i = 0

    while i < len(history):
        item = history[i]
        item_type = item.get("type")

        if item_type == "message":
            role = "user" if item.get("role") == "user" else "model"
            parts = _convert_message_content_to_parts(item.get("content", []))
            if parts:
                contents.append(types.Content(role=role, parts=parts))
            i += 1

        elif item_type == "function_call":
            # Collect all consecutive function calls into one model turn
            parts = []
            while i < len(history) and history[i].get("type") == "function_call":
                fc_item = history[i]
                part = _convert_function_call_to_part(fc_item)
                if part:
                    parts.append(part)
                i += 1

            if parts:
                contents.append(types.Content(role="model", parts=parts))

        elif item_type == "function_call_output":
            # Collect all consecutive function outputs into one user turn
            parts = []
            # We need to track function names for outputs (they reference call_id)
            call_id_to_name = _build_call_id_to_name_map(history)

            while i < len(history) and history[i].get("type") == "function_call_output":
                out_item = history[i]
                part = _convert_function_output_to_part(out_item, call_id_to_name)
                if part:
                    parts.append(part)
                i += 1

            if parts:
                contents.append(types.Content(role="user", parts=parts))

        else:
            # Skip unknown types
            logger.debug(f"Skipping unknown history item type: {item_type}")
            i += 1

    return contents


def _convert_message_content_to_parts(content: Any) -> List[types.Part]:
    """Convert message content to list of Parts.

    Handles both string content and structured content arrays.
    """
    parts = []

    if isinstance(content, str):
        if content:
            parts.append(types.Part(text=content))
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text = item.get("text", "")
                    if text:
                        parts.append(types.Part(text=text))
                elif item.get("type") == "input_text":
                    # Alternative format
                    text = item.get("text", "")
                    if text:
                        parts.append(types.Part(text=text))

    return parts


def _convert_function_call_to_part(fc_item: Dict[str, Any]) -> Optional[types.Part]:
    """Convert a function_call item to a Part with FunctionCall.

    Preserves thought_signature if present.
    """
    name = fc_item.get("name")
    if not name:
        logger.warning("Function call missing name, skipping")
        return None

    # Parse arguments
    args_raw = fc_item.get("arguments", "{}")
    if isinstance(args_raw, str):
        try:
            args = json.loads(args_raw) if args_raw else {}
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse function arguments: {args_raw}")
            args = {}
    else:
        args = args_raw or {}

    # Create FunctionCall
    function_call = types.FunctionCall(
        name=name,
        args=args,
        id=fc_item.get("call_id"),
    )

    # Handle thought_signature
    thought_sig = fc_item.get("thought_signature")
    if thought_sig:
        # Convert to bytes if string
        if isinstance(thought_sig, str):
            thought_bytes = thought_sig.encode("utf-8")
        else:
            thought_bytes = thought_sig
        return types.Part(function_call=function_call, thought_signature=thought_bytes)
    else:
        return types.Part(function_call=function_call)


def _convert_function_output_to_part(
    out_item: Dict[str, Any], call_id_to_name: Dict[str, str]
) -> Optional[types.Part]:
    """Convert a function_call_output item to a Part with FunctionResponse."""
    call_id = out_item.get("call_id")
    output = out_item.get("output", "")

    # Look up function name from call_id
    name = call_id_to_name.get(call_id or "", "")
    if not name:
        # Try to get name directly from the output item (some formats include it)
        name = out_item.get("name", "unknown")

    # Create FunctionResponse
    function_response = types.FunctionResponse(
        id=call_id,
        name=name,
        response={"result": output},
    )

    return types.Part(function_response=function_response)


def _build_call_id_to_name_map(history: List[Dict[str, Any]]) -> Dict[str, str]:
    """Build a mapping from call_id to function name from history."""
    mapping = {}
    for item in history:
        if item.get("type") == "function_call":
            call_id = item.get("call_id")
            name = item.get("name")
            if call_id and name:
                mapping[call_id] = name
    return mapping


def content_to_responses(content: types.Content) -> List[Dict[str, Any]]:
    """Convert a google-genai Content to Responses API format items.

    A single Content may produce multiple Responses API items
    (e.g., text + function_call in same Content).

    Args:
        content: google-genai Content object

    Returns:
        List of Responses API format dictionaries
    """
    items = []
    role = content.role if content.role else "model"
    responses_role = "user" if role == "user" else "assistant"

    text_parts = []
    function_calls = []
    function_responses = []

    for part in content.parts or []:
        if part.text:
            text_parts.append({"type": "text", "text": part.text})

        if part.function_call:
            fc = part.function_call
            fc_item = {
                "type": "function_call",
                "name": fc.name,
                "arguments": json.dumps(fc.args) if fc.args else "{}",
                "call_id": fc.id,
            }
            # Preserve thought_signature
            if part.thought_signature:
                if isinstance(part.thought_signature, bytes):
                    fc_item["thought_signature"] = part.thought_signature.decode(
                        "utf-8"
                    )
                else:
                    fc_item["thought_signature"] = str(part.thought_signature)
            function_calls.append(fc_item)

        if part.function_response:
            fr = part.function_response
            output = ""
            if fr.response:
                if isinstance(fr.response, dict):
                    output = fr.response.get("result", str(fr.response))
                else:
                    output = str(fr.response)

            fr_item = {
                "type": "function_call_output",
                "call_id": fr.id,
                "name": fr.name,
                "output": output,
            }
            function_responses.append(fr_item)

    # Add text content as message if present
    if text_parts:
        items.append(
            {
                "type": "message",
                "role": responses_role,
                "content": text_parts,
            }
        )

    # Add function calls
    items.extend(function_calls)

    # Add function responses
    items.extend(function_responses)

    return items


def tools_to_gemini(tools: List[Dict[str, Any]]) -> List[types.Tool]:
    """Convert OpenAI-format tool declarations to Gemini types.Tool.

    OpenAI format:
    {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}

    Gemini format:
    types.Tool(function_declarations=[types.FunctionDeclaration(...)])

    Args:
        tools: List of OpenAI-format tool declarations

    Returns:
        List of google-genai Tool objects
    """
    if not tools:
        return []

    declarations = []

    for tool in tools:
        if tool.get("type") != "function":
            continue

        func = tool.get("function", {})
        name = func.get("name")
        if not name:
            continue

        # Create FunctionDeclaration
        # The SDK handles JSON Schema → Gemini Schema conversion
        decl = types.FunctionDeclaration(
            name=name,
            description=func.get("description", ""),
            parameters=func.get("parameters"),
        )
        declarations.append(decl)

    if declarations:
        return [types.Tool(function_declarations=declarations)]

    return []


def extract_text_from_response(response: types.GenerateContentResponse) -> str:
    """Extract text content from a GenerateContentResponse.

    Args:
        response: google-genai GenerateContentResponse

    Returns:
        Extracted text content, or empty string if none
    """
    if not response.candidates:
        return ""

    parts_text = []
    for candidate in response.candidates:
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.text:
                    parts_text.append(part.text)

    return "\n".join(parts_text)


def extract_function_calls(
    response: types.GenerateContentResponse,
) -> List[types.Part]:
    """Extract Parts containing function calls from response.

    Preserves the Part objects to maintain thought_signature.

    Args:
        response: google-genai GenerateContentResponse

    Returns:
        List of Part objects that have function_call set
    """
    function_call_parts: list[types.Part] = []

    if not response.candidates:
        return function_call_parts

    for candidate in response.candidates:
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.function_call:
                    function_call_parts.append(part)

    return function_call_parts

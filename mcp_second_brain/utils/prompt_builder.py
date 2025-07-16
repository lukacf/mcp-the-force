from __future__ import annotations
from typing import List, Tuple, Optional, Any
from lxml import etree as ET
import time
import logging
from ..config import get_settings
from .fs import gather_file_paths
from ..adapters.model_registry import get_model_context_window
from .context_loader import load_text_files

logger = logging.getLogger(__name__)

_set = get_settings()


def _create_file_element(
    path: str, content: str
) -> Any:  # ET.Element is not a valid type annotation
    el = ET.Element("file", path=path)
    # Ensure content is safe for XML
    # Remove any remaining control characters except tab, newline, carriage return
    safe_content = "".join(
        char for char in content if ord(char) >= 32 or char in "\t\n\r"
    )
    el.text = safe_content
    return el


def build_prompt(
    instr: str,
    out_fmt: str,
    ctx: List[str],
    attach: List[str] | None = None,
    model: Optional[str] = None,
) -> Tuple[str, List[str]]:
    # Short circuit if no context provided
    if not ctx and not attach:
        task = ET.Element("Task")
        ET.SubElement(task, "Instructions").text = instr
        ET.SubElement(task, "OutputFormat").text = out_fmt
        ET.SubElement(task, "CONTEXT").text = ""
        prompt = ET.tostring(task, encoding="unicode")
        return prompt, []

    gather_start = time.time()
    logger.info(f"DEBUG build_prompt: ctx={ctx}, attach={attach}")
    ctx_files = gather_file_paths(ctx) if ctx else []
    logger.info(
        f"Gathered {len(ctx_files)} context files in {time.time() - gather_start:.2f}s - files: {ctx_files}"
    )

    extras = gather_file_paths(attach) if attach else []
    logger.info(f"Gathered {len(extras)} attachment files - files: {extras}")

    # Get context limit based on model and configured percentage
    model_limit = get_model_context_window(model or "")
    context_percentage = _set.context_percentage

    # Calculate limit with safety margin
    max_tokens = int(model_limit * context_percentage)
    # Additional safety margin for system prompts, tool calls, etc.
    safety_margin = 2000  # Reserve 2k tokens for overhead
    max_tokens = max(max_tokens - safety_margin, 1000)  # Ensure at least 1k tokens

    logger.info(
        f"Using context limit of {max_tokens:,} tokens for model {model} ({context_percentage:.0%} of {model_limit:,} minus {safety_margin} safety margin)"
    )

    inline_elements, attachments, used = [], [], 0

    # For large context models, try to inline everything
    all_files = ctx_files + [f for f in extras if f not in ctx_files]
    logger.info(f"[PROMPT_BUILDER] Total files to process: {len(all_files)}")

    # Use the shared context loader to get file contents and token counts
    logger.info(f"[PROMPT_BUILDER] Calling load_text_files with {len(all_files)} files")
    file_data = load_text_files(all_files)
    logger.info(
        f"[PROMPT_BUILDER] load_text_files returned {len(file_data)} loaded files"
    )

    logger.info(f"[PROMPT_BUILDER] Processing {len(file_data)} files for inlining")
    for i, (file_path, content, token_count) in enumerate(file_data):
        if i % 50 == 0:  # Log progress every 50 files
            logger.info(
                f"[PROMPT_BUILDER] Processing file {i + 1}/{len(file_data)}: {file_path} ({token_count} tokens)"
            )
        if used + token_count <= max_tokens:
            inline_elements.append(_create_file_element(file_path, content))
            used += token_count
        else:
            # Only use vector store if we exceed model's context limit
            attachments.append(file_path)

    # Also add any files that couldn't be loaded
    loaded_paths = {item[0] for item in file_data}
    for f in all_files:
        if f not in loaded_paths:
            attachments.append(f)

    logger.info(
        f"Inlined {len(inline_elements)} files ({used:,} tokens), {len(attachments)} files for vector store"
    )

    task = ET.Element("Task")
    ET.SubElement(task, "Instructions").text = instr
    ET.SubElement(task, "OutputFormat").text = out_fmt
    CTX = ET.SubElement(task, "CONTEXT")

    # Append file elements directly (no parsing needed)
    for elem in inline_elements:
        CTX.append(elem)

    prompt = ET.tostring(task, encoding="unicode")
    logger.info(f"[PROMPT_BUILDER] Final prompt built: {len(prompt)} chars")
    if attachments:
        prompt += "\n\nYou have additional information accessible through the file search tool."

    return prompt, attachments

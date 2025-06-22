from __future__ import annotations
from pathlib import Path
from typing import List, Tuple, Optional
from lxml import etree as ET
import time
import logging
from ..config import get_settings
from .token_counter import count_tokens
from .fs import gather_file_paths

logger = logging.getLogger(__name__)

_set = get_settings()

# Model context windows (actual limits)
MODEL_CONTEXT_LIMITS = {
    "gemini-2.5-pro": 1_000_000,  # 1M tokens
    "gemini-2.5-flash": 1_000_000,  # 1M tokens
    "gpt-4.1": 1_000_000,  # 1M tokens
    "o3": 200_000,  # 200k tokens
    "o3-pro": 200_000,  # 200k tokens
}


def _create_file_element(path: str, content: str) -> ET.Element:
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
    ctx_files = gather_file_paths(ctx) if ctx else []
    logger.info(
        f"Gathered {len(ctx_files)} context files in {time.time() - gather_start:.2f}s"
    )

    extras = gather_file_paths(attach) if attach else []
    logger.info(f"Gathered {len(extras)} attachment files")

    # Get context limit based on model and configured percentage
    model_limit = MODEL_CONTEXT_LIMITS.get(
        model, 32_000
    )  # Conservative fallback for unknown models
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

    for f in all_files:
        try:
            txt = Path(f).read_text(encoding="utf-8", errors="ignore")
            # Remove NULL bytes which are not allowed in XML
            if "\x00" in txt:
                txt = txt.replace("\x00", "")
                logger.debug(f"Removed NULL bytes from {f}")

            tok = count_tokens([txt])

            if used + tok <= max_tokens:
                inline_elements.append(_create_file_element(f, txt))
                used += tok
            else:
                # Only use vector store if we exceed model's context limit
                attachments.append(f)
        except Exception as e:
            logger.warning(f"Error reading file {f}: {e}")
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
    if attachments:
        prompt += "\n\nYou have additional information accessible through the file search tool."

    return prompt, attachments

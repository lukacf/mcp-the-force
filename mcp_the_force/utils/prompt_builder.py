"""Simple prompt builder for backwards compatibility."""

from __future__ import annotations
from typing import List, Tuple, Any
from lxml import etree as ET
import logging
from .fs import gather_file_paths
from .context_loader import load_text_files

logger = logging.getLogger(__name__)


def _create_file_element(path: str, content: str) -> Any:
    """Create XML element for a file."""
    el = ET.Element("file", path=path)
    # Ensure content is safe for XML
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
) -> Tuple[str, List[str]]:
    """Build XML prompt from instructions, output format, and context files.

    This is used only when session_id is not provided (backwards compatibility).
    The modern path uses build_context_with_stable_list.
    """
    # Short circuit if no context provided
    if not ctx and not attach:
        task = ET.Element("Task")
        ET.SubElement(task, "Instructions").text = instr
        ET.SubElement(task, "OutputFormat").text = out_fmt
        ET.SubElement(task, "CONTEXT").text = ""
        prompt = ET.tostring(task, encoding="unicode")
        return prompt, []

    # Gather all files
    ctx_files = gather_file_paths(ctx) if ctx else []
    extras = gather_file_paths(attach) if attach else []
    all_files = ctx_files + [f for f in extras if f not in ctx_files]

    # Load and inline all files
    file_data = load_text_files(all_files)
    inline_elements = []
    for file_path, content, _ in file_data:
        inline_elements.append(_create_file_element(file_path, content))

    # Build XML prompt
    task = ET.Element("Task")
    ET.SubElement(task, "Instructions").text = instr
    ET.SubElement(task, "OutputFormat").text = out_fmt
    CTX = ET.SubElement(task, "CONTEXT")

    for elem in inline_elements:
        CTX.append(elem)

    prompt = ET.tostring(task, encoding="unicode")
    return prompt, []

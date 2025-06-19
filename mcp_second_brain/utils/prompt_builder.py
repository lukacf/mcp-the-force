from __future__ import annotations
from pathlib import Path
from typing import List, Tuple
from lxml import etree as ET
import time
import logging
from ..config import get_settings
from .token_counter import count_tokens
from .fs import gather_file_paths

logger = logging.getLogger(__name__)

_set = get_settings()

def _create_file_element(path: str, content: str) -> ET.Element:
    el = ET.Element("file", path=path)
    el.text = content
    return el

def build_prompt(instr: str, out_fmt: str, ctx: List[str], attach: List[str] | None = None) -> Tuple[str, List[str]]:
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
    logger.info(f"Gathered {len(ctx_files)} context files in {time.time() - gather_start:.2f}s")
    
    extras = gather_file_paths(attach) if attach else []
    logger.info(f"Gathered {len(extras)} attachment files")
    
    inline_elements, attachments, used = [], [], 0
    
    for f in ctx_files:
        txt = Path(f).read_text(encoding="utf-8", errors="ignore")
        tok = count_tokens([txt])
        
        if used + tok <= _set.max_inline_tokens:
            inline_elements.append(_create_file_element(f, txt))
            used += tok
        else:
            attachments.append(f)
    
    for f in extras:
        if f not in attachments and f not in ctx_files:
            attachments.append(f)
    
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
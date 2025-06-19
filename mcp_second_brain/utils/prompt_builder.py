from __future__ import annotations
import html
from pathlib import Path
from typing import List, Tuple
from lxml import etree as ET
from ..config import get_settings
from .token_counter import count_tokens
from .fs import gather_file_paths

_set = get_settings()

def _tag(path: str, content: str) -> str:
    el = ET.Element("file", path=path)
    el.text = content
    return ET.tostring(el, encoding="unicode")

def build_prompt(instr: str, out_fmt: str, ctx: List[str], attach: List[str] | None = None) -> Tuple[str, List[str]]:
    # Short circuit if no context provided
    if not ctx and not attach:
        task = ET.Element("Task")
        ET.SubElement(task, "Instructions").text = instr
        ET.SubElement(task, "OutputFormat").text = out_fmt
        ET.SubElement(task, "CONTEXT").text = ""
        prompt = ET.tostring(task, encoding="unicode")
        return prompt, []
    
    ctx_files = gather_file_paths(ctx) if ctx else []
    extras = gather_file_paths(attach) if attach else []
    
    inline, attachments, used = [], [], 0
    
    for f in ctx_files:
        txt = Path(f).read_text(encoding="utf-8", errors="ignore")
        tok = count_tokens([txt])
        
        if used + tok <= _set.max_inline_tokens:
            inline.append(_tag(f, html.escape(txt)))
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
    if inline:
        # Parse the XML strings and append as children
        for xml_str in inline:
            file_elem = ET.fromstring(xml_str)
            CTX.append(file_elem)
    else:
        CTX.text = ""
    
    prompt = ET.tostring(task, encoding="unicode")
    if attachments:
        prompt += "\n\nYou have additional information accessible through the file search tool."
    
    return prompt, attachments
#!/usr/bin/env python3
"""MCP Second-Brain Server using FastMCP."""
from mcp.server.fastmcp import FastMCP
from typing import List, Dict, Any, Optional

from .adapters import OpenAIAdapter, VertexAdapter
from .utils.prompt_builder import build_prompt
from .utils.vector_store import create_vector_store
from .config import get_settings

# Initialize FastMCP server
mcp = FastMCP("mcp-second-brain")

# Lazy adapter initialization
adapters = {}

def get_adapter(name: str):
    """Get or create an adapter lazily."""
    if name not in adapters:
        try:
            if name == "deep-multimodal-reasoner":
                adapters[name] = VertexAdapter("gemini-2.5-pro")
            elif name == "flash-summary-sprinter":
                adapters[name] = VertexAdapter("gemini-2.5-flash")
            elif name == "chain-of-thought-helper":
                adapters[name] = OpenAIAdapter("o3")
            elif name == "slow-and-sure-thinker":
                adapters[name] = OpenAIAdapter("o3-pro")
            elif name == "fast-long-context-assistant":
                adapters[name] = OpenAIAdapter("gpt-4.1")
        except Exception as e:
            return None, str(e)
    return adapters.get(name), None

# Tool descriptions
tool_descriptions = {
    "deep-multimodal-reasoner": "Deep multimodal reasoner for bug fixing and complex reasoning (Gemini 2.5 Pro, ctx≈2000k)",
    "flash-summary-sprinter": "Flash summary sprinter for fast summarization (Gemini 2.5 Flash, ctx≈2000k)",
    "chain-of-thought-helper": "Chain-of-thought helper for algorithm design (OpenAI o3, ctx≈200k)",
    "slow-and-sure-thinker": "Slow and sure thinker for formal proofs and deep analysis (OpenAI o3-pro, ctx≈200k)",
    "fast-long-context-assistant": "Fast long-context assistant for large-scale refactoring (GPT-4.1, ctx≈1000k)"
}

@mcp.tool()
def deep_multimodal_reasoner(
    instructions: str,
    output_format: str,
    context: List[str],
    attachments: Optional[List[str]] = None,
    temperature: Optional[float] = None,
    reasoning_effort: Optional[str] = None,
    max_reasoning_tokens: Optional[int] = None
) -> str:
    """Deep multimodal reasoner for bug fixing and complex reasoning (Gemini 2.5 Pro, ctx≈2000k).
    
    Example: {"instructions":"Fix bug","output_format":"diffs","context":["/absolute/path/to/src/"]}
    
    Note: Use absolute paths in context and attachments for reliable results.
    """
    adapter, error = get_adapter("deep-multimodal-reasoner")
    if not adapter:
        return f"Error: Failed to initialize Vertex AI adapter. {error}"
    
    prompt, attach = build_prompt(instructions, output_format, context, attachments)
    vs = [create_vector_store(attach)] if attach else None
    
    extra = {}
    if temperature is not None:
        extra["temperature"] = temperature
    if reasoning_effort:
        extra["reasoning_effort"] = reasoning_effort
    if max_reasoning_tokens:
        extra["max_reasoning_tokens"] = max_reasoning_tokens
    
    return adapter.generate(prompt, vector_store_ids=vs, **extra)

@mcp.tool()
def flash_summary_sprinter(
    instructions: str,
    output_format: str,
    context: List[str],
    attachments: Optional[List[str]] = None,
    temperature: Optional[float] = None
) -> str:
    """Flash summary sprinter for fast summarization (Gemini 2.5 Flash, ctx≈2000k).
    
    Example: {"instructions":"Summarise logs","output_format":"bullets","context":["/absolute/path/to/logs/"]}
    
    Note: Use absolute paths in context and attachments for reliable results.
    """
    adapter, error = get_adapter("flash-summary-sprinter")
    if not adapter:
        return f"Error: Failed to initialize Vertex AI adapter. {error}"
    
    prompt, attach = build_prompt(instructions, output_format, context, attachments)
    vs = [create_vector_store(attach)] if attach else None
    
    extra = {}
    if temperature is not None:
        extra["temperature"] = temperature
    
    return adapter.generate(prompt, vector_store_ids=vs, **extra)

@mcp.tool()
def chain_of_thought_helper(
    instructions: str,
    output_format: str,
    context: List[str],
    attachments: Optional[List[str]] = None,
    temperature: Optional[float] = None,
    reasoning_effort: Optional[str] = None,
    max_reasoning_tokens: Optional[int] = None
) -> str:
    """Chain-of-thought helper for algorithm design (OpenAI o3, ctx≈200k).
    
    Example: {"instructions":"Design algo","output_format":"steps","context":["/absolute/path/to/project/"]}
    
    Note: Use absolute paths in context and attachments for reliable results.
    """
    adapter, error = get_adapter("chain-of-thought-helper")
    if not adapter:
        return f"Error: Failed to initialize OpenAI adapter. {error}"
    
    prompt, attach = build_prompt(instructions, output_format, context, attachments)
    vs = [create_vector_store(attach)] if attach else None
    
    extra = {}
    if temperature is not None:
        extra["temperature"] = temperature
    if reasoning_effort:
        extra["reasoning_effort"] = reasoning_effort
    if max_reasoning_tokens:
        extra["max_reasoning_tokens"] = max_reasoning_tokens
    
    return adapter.generate(prompt, vector_store_ids=vs, **extra)

@mcp.tool()
def slow_and_sure_thinker(
    instructions: str,
    output_format: str,
    context: List[str],
    attachments: Optional[List[str]] = None,
    temperature: Optional[float] = None,
    reasoning_effort: Optional[str] = None,
    max_reasoning_tokens: Optional[int] = None
) -> str:
    """Slow and sure thinker for formal proofs and deep analysis (OpenAI o3-pro, ctx≈200k).
    
    Example: {"instructions":"Prove X","output_format":"proof","context":["/absolute/path/to/doc.md"]}
    
    Note: Use absolute paths in context and attachments for reliable results.
    """
    adapter, error = get_adapter("slow-and-sure-thinker")
    if not adapter:
        return f"Error: Failed to initialize OpenAI adapter. {error}"
    
    prompt, attach = build_prompt(instructions, output_format, context, attachments)
    vs = [create_vector_store(attach)] if attach else None
    
    extra = {}
    if temperature is not None:
        extra["temperature"] = temperature
    if reasoning_effort:
        extra["reasoning_effort"] = reasoning_effort
    if max_reasoning_tokens:
        extra["max_reasoning_tokens"] = max_reasoning_tokens
    
    return adapter.generate(prompt, vector_store_ids=vs, **extra)

@mcp.tool()
def fast_long_context_assistant(
    instructions: str,
    output_format: str,
    context: List[str],
    attachments: Optional[List[str]] = None,
    temperature: Optional[float] = None
) -> str:
    """Fast long-context assistant for large-scale refactoring (GPT-4.1, ctx≈1000k).
    
    Example: {"instructions":"Refactor","output_format":"patches","context":["/absolute/path/to/src/"]}
    
    Note: Use absolute paths in context and attachments for reliable results.
    """
    adapter, error = get_adapter("fast-long-context-assistant")
    if not adapter:
        return f"Error: Failed to initialize OpenAI adapter. {error}"
    
    prompt, attach = build_prompt(instructions, output_format, context, attachments)
    vs = [create_vector_store(attach)] if attach else None
    
    extra = {}
    if temperature is not None:
        extra["temperature"] = temperature
    
    return adapter.generate(prompt, vector_store_ids=vs, **extra)

def main():
    """Main entry point for the MCP server."""
    mcp.run()

if __name__ == "__main__":
    main()
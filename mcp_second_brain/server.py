#!/usr/bin/env python3
"""MCP Second-Brain Server using FastMCP."""
from mcp.server.fastmcp import FastMCP
from typing import List, Dict, Any, Optional
import time
import logging
import asyncio

# Enable asyncio debug mode
asyncio.get_event_loop().set_debug(True)
_logging = logging.getLogger("asyncio")
_logging.setLevel(logging.INFO)

from .adapters import OpenAIAdapter, VertexAdapter
from .utils.prompt_builder import build_prompt
from .utils.vector_store import create_vector_store, delete_vector_store
from .config import get_settings

# Set up file logging with non-blocking handler
import os
from logging.handlers import QueueHandler, QueueListener
import queue

log_file = os.path.expanduser("~/mcp-second-brain-debug.log")

# Create a queue for logging
log_queue = queue.Queue()

# Create file handler with delay=True to avoid blocking
file_handler = logging.FileHandler(log_file, delay=True)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Create queue handler and listener
queue_handler = QueueHandler(log_queue)
queue_listener = QueueListener(log_queue, file_handler, console_handler)
queue_listener.start()

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[queue_handler]
)
logger = logging.getLogger(__name__)
logger.info(f"MCP Second-Brain server starting, logs written to {log_file}")

# Initialize FastMCP server
mcp = FastMCP("mcp-second-brain")

# Lazy adapter initialization
adapters = {}

# Simple session cache for OpenAI response IDs
class SessionCache:
    """Minimal ephemeral cache for OpenAI response IDs."""
    def __init__(self, ttl=3600):
        self._data = {}
        self.ttl = ttl
    
    def get_response_id(self, session_id: str) -> Optional[str]:
        """Get the previous response ID for a session."""
        self._gc()
        session = self._data.get(session_id)
        if session and time.time() - session['updated'] < self.ttl:
            return session.get('response_id')
        return None
    
    def set_response_id(self, session_id: str, response_id: str):
        """Store a response ID for a session."""
        self._data[session_id] = {
            'response_id': response_id,
            'updated': time.time()
        }
    
    def _gc(self):
        """Garbage collect expired sessions."""
        now = time.time()
        self._data = {k: v for k, v in self._data.items() 
                      if now - v['updated'] < self.ttl}

session_cache = SessionCache()

# Tool name to model mapping
TOOL_TO_MODEL = {
    "deep-multimodal-reasoner": "gemini-2.5-pro",
    "flash-summary-sprinter": "gemini-2.5-flash",
    "chain-of-thought-helper": "o3",
    "slow-and-sure-thinker": "o3-pro",
    "fast-long-context-assistant": "gpt-4.1"
}

# Model-specific timeouts (in seconds)
MODEL_TIMEOUTS = {
    "gemini-2.5-pro": 600,      # 10 minutes
    "gemini-2.5-flash": 300,    # 5 minutes
    "gpt-4.1": 300,             # 5 minutes
    "o3": 600,                  # 10 minutes
    "o3-pro": 2700,             # 45 minutes
}

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
async def deep_multimodal_reasoner(
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
    
    prompt, attach = await asyncio.wait_for(
        asyncio.to_thread(
            build_prompt, instructions, output_format, context, attachments, model=TOOL_TO_MODEL["deep-multimodal-reasoner"]
        ),
        timeout=5
    )
    # Gemini models don't support vector stores - attachments are inlined in prompt
    vs = None
    
    extra = {}
    if temperature is not None:
        extra["temperature"] = temperature
    if reasoning_effort:
        extra["reasoning_effort"] = reasoning_effort
    if max_reasoning_tokens:
        extra["max_reasoning_tokens"] = max_reasoning_tokens
    
    
    model = TOOL_TO_MODEL["deep-multimodal-reasoner"]
    timeout = MODEL_TIMEOUTS.get(model, 600)
    return await asyncio.wait_for(
        adapter.generate(prompt, vector_store_ids=vs, **extra),
        timeout=timeout
    )

@mcp.tool()
async def flash_summary_sprinter(
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
    
    prompt, attach = await asyncio.wait_for(
        asyncio.to_thread(
            build_prompt, instructions, output_format, context, attachments, model=TOOL_TO_MODEL["flash-summary-sprinter"]
        ),
        timeout=5
    )
    # Gemini models don't support vector stores - attachments are inlined in prompt
    vs = None
    
    extra = {}
    if temperature is not None:
        extra["temperature"] = temperature
    
    
    model = TOOL_TO_MODEL["flash-summary-sprinter"]
    timeout = MODEL_TIMEOUTS.get(model, 300)
    return await asyncio.wait_for(
        adapter.generate(prompt, vector_store_ids=vs, **extra),
        timeout=timeout
    )

@mcp.tool()
async def chain_of_thought_helper(
    instructions: str,
    output_format: str,
    context: List[str],
    attachments: Optional[List[str]] = None,
    temperature: Optional[float] = None,
    reasoning_effort: Optional[str] = None,
    max_reasoning_tokens: Optional[int] = None,
    session_id: Optional[str] = None
) -> str:
    """Chain-of-thought helper for algorithm design (OpenAI o3, ctx≈200k).
    
    Example: {"instructions":"Design algo","output_format":"steps","context":["/absolute/path/to/project/"]}
    
    Note: Use absolute paths in context and attachments for reliable results.
    """
    adapter, error = get_adapter("chain-of-thought-helper")
    if not adapter:
        return f"Error: Failed to initialize OpenAI adapter. {error}"
    
    prompt, attach = await asyncio.wait_for(
        asyncio.to_thread(
            build_prompt, instructions, output_format, context, attachments, model=TOOL_TO_MODEL["chain-of-thought-helper"]
        ),
        timeout=5
    )
    vs_id = create_vector_store(attach) if attach else None
    vs = [vs_id] if vs_id else None
    
    extra = {}
    if temperature is not None:
        extra["temperature"] = temperature
    if reasoning_effort:
        extra["reasoning_effort"] = reasoning_effort
    if max_reasoning_tokens:
        extra["max_reasoning_tokens"] = max_reasoning_tokens
    
    try:
        model = TOOL_TO_MODEL["chain-of-thought-helper"]
        timeout = MODEL_TIMEOUTS.get(model, 600)
        
        # Get previous response ID if session provided
        previous_response_id = None
        if session_id:
            previous_response_id = session_cache.get_response_id(session_id)
        
        result = await asyncio.wait_for(
            adapter.generate(prompt, vector_store_ids=vs, 
                           previous_response_id=previous_response_id, **extra),
            timeout=timeout
        )
        
        # Handle the response based on type
        if isinstance(result, dict):
            content = result.get("content", "")
            # Store response ID for next call if session provided
            if session_id and "response_id" in result:
                session_cache.set_response_id(session_id, result["response_id"])
            return content
        else:
            # Vertex adapter returns string directly
            return result
    finally:
        # Clean up vector store
        if vs_id:
            delete_vector_store(vs_id)

@mcp.tool()
async def slow_and_sure_thinker(
    instructions: str,
    output_format: str,
    context: List[str],
    attachments: Optional[List[str]] = None,
    temperature: Optional[float] = None,
    reasoning_effort: Optional[str] = None,
    max_reasoning_tokens: Optional[int] = None,
    session_id: Optional[str] = None
) -> str:
    """Slow and sure thinker for formal proofs and deep analysis (OpenAI o3-pro, ctx≈200k).
    
    Example: {"instructions":"Prove X","output_format":"proof","context":["/absolute/path/to/doc.md"]}
    
    Note: Use absolute paths in context and attachments for reliable results.
    """
    adapter, error = get_adapter("slow-and-sure-thinker")
    if not adapter:
        return f"Error: Failed to initialize OpenAI adapter. {error}"
    
    prompt, attach = await asyncio.wait_for(
        asyncio.to_thread(
            build_prompt, instructions, output_format, context, attachments, model=TOOL_TO_MODEL["slow-and-sure-thinker"]
        ),
        timeout=5
    )
    vs_id = create_vector_store(attach) if attach else None
    vs = [vs_id] if vs_id else None
    
    extra = {}
    if temperature is not None:
        extra["temperature"] = temperature
    if reasoning_effort:
        extra["reasoning_effort"] = reasoning_effort
    if max_reasoning_tokens:
        extra["max_reasoning_tokens"] = max_reasoning_tokens
    
    try:
        model = TOOL_TO_MODEL["slow-and-sure-thinker"]
        timeout = MODEL_TIMEOUTS.get(model, 2700)
        
        # Get previous response ID if session provided
        previous_response_id = None
        if session_id:
            previous_response_id = session_cache.get_response_id(session_id)
        
        result = await asyncio.wait_for(
            adapter.generate(prompt, vector_store_ids=vs,
                           previous_response_id=previous_response_id, **extra),
            timeout=timeout
        )
        
        # Handle the response based on type
        if isinstance(result, dict):
            content = result.get("content", "")
            # Store response ID for next call if session provided
            if session_id and "response_id" in result:
                session_cache.set_response_id(session_id, result["response_id"])
            return content
        else:
            # Vertex adapter returns string directly
            return result
    finally:
        # Clean up vector store
        if vs_id:
            delete_vector_store(vs_id)

@mcp.tool()
async def fast_long_context_assistant(
    instructions: str,
    output_format: str,
    context: List[str],
    attachments: Optional[List[str]] = None,
    temperature: Optional[float] = None,
    session_id: Optional[str] = None
) -> str:
    """Fast long-context assistant for large-scale refactoring (GPT-4.1, ctx≈1000k).
    
    Example: {"instructions":"Refactor","output_format":"patches","context":["/absolute/path/to/src/"]}
    
    Note: Use absolute paths in context and attachments for reliable results.
    """
    start_time = time.time()
    logger.info(f"fast_long_context_assistant called with context: {context}, attachments: {attachments}")
    
    adapter, error = get_adapter("fast-long-context-assistant")
    if not adapter:
        return f"Error: Failed to initialize OpenAI adapter. {error}"
    
    logger.info(f"Adapter initialized in {time.time() - start_time:.2f}s")
    
    build_start = time.time()
    prompt, attach = await asyncio.wait_for(
        asyncio.to_thread(
            build_prompt, instructions, output_format, context, attachments, model="gpt-4.1"
        ),
        timeout=5
    )
    logger.info(f"Prompt built in {time.time() - build_start:.2f}s, attach files: {len(attach) if attach else 0}")
    logger.debug(f"Prompt length: {len(prompt)} chars")
    
    vs_start = time.time()
    vs_id = create_vector_store(attach) if attach else None
    vs = [vs_id] if vs_id else None
    logger.info(f"Vector store created in {time.time() - vs_start:.2f}s")
    
    extra = {}
    if temperature is not None:
        extra["temperature"] = temperature
    
    gen_start = time.time()
    logger.info(f"Sending request to OpenAI API...")
    try:
        model = TOOL_TO_MODEL["fast-long-context-assistant"]
        timeout = MODEL_TIMEOUTS.get(model, 300)
        
        # Get previous response ID if session provided
        previous_response_id = None
        if session_id:
            previous_response_id = session_cache.get_response_id(session_id)
        
        result = await asyncio.wait_for(
            adapter.generate(prompt, vector_store_ids=vs,
                           previous_response_id=previous_response_id, **extra),
            timeout=timeout
        )
        logger.info(f"Generation completed in {time.time() - gen_start:.2f}s")
        logger.info(f"Total time: {time.time() - start_time:.2f}s")
        
        # Handle the response based on type
        if isinstance(result, dict):
            content = result.get("content", "")
            # Store response ID for next call if session provided
            if session_id and "response_id" in result:
                session_cache.set_response_id(session_id, result["response_id"])
            return content
        else:
            # Vertex adapter returns string directly
            return result
    finally:
        # Clean up vector store
        if vs_id:
            delete_vector_store(vs_id)

# Vector store management tools
@mcp.tool()
async def create_vector_store_tool(
    files: List[str],
    name: Optional[str] = None
) -> Dict[str, str]:
    """Create a vector store from files and return its ID.
    
    Args:
        files: List of file paths to include in the vector store
        name: Optional name for the vector store
        
    Returns:
        Dictionary with vector_store_id
    """
    try:
        vs_id = await asyncio.to_thread(create_vector_store, files)
        if vs_id:
            return {"vector_store_id": vs_id, "status": "created"}
        else:
            return {"vector_store_id": "", "status": "no_supported_files"}
    except Exception as e:
        logger.error(f"Error creating vector store: {e}")
        return {"vector_store_id": "", "status": "error", "error": str(e)}

def main():
    """Main entry point for the MCP server."""
    mcp.run()

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""Dynamic MCP Second-Brain Server with config-driven tools."""
from mcp.server.fastmcp import FastMCP
from typing import List, Optional, Dict, Any
import asyncio
import logging
import time

from .config import load_models, ModelConfig
from .adapters import get_adapter
from .utils.prompt_builder import build_prompt
from .utils.vector_store import create_vector_store, delete_vector_store
from .session_cache import session_cache

# Set up logging
import os
from logging.handlers import QueueHandler, QueueListener
import queue

log_file = os.path.expanduser("~/mcp-second-brain-debug.log")
log_queue = queue.Queue()
file_handler = logging.FileHandler(log_file, delay=True)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
queue_handler = QueueHandler(log_queue)
queue_listener = QueueListener(log_queue, file_handler, console_handler)
queue_listener.start()

logging.basicConfig(level=logging.INFO, handlers=[queue_handler])
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("mcp-second-brain")

# Load model configurations
try:
    MODELS = load_models()
    logger.info(f"Loaded {len(MODELS)} model configurations")
except Exception as e:
    logger.error(f"Failed to load model configurations: {e}")
    MODELS = {}

def create_tool_function(cfg: ModelConfig):
    """Create a tool function for a given model configuration."""
    
    async def tool_function(
        instructions: str,
        output_format: str,
        context: List[str],
        attachments: Optional[List[str]] = None,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
        max_reasoning_tokens: Optional[int] = None,
        session_id: Optional[str] = None
    ) -> str:
        """Dynamic tool function generated from model config."""
        start_time = time.time()
        logger.info(f"{cfg.id} called with context: {len(context)} files")
        
        # Get adapter
        adapter, error = get_adapter(cfg.adapter, cfg.model_name)
        if not adapter:
            return f"Error: Failed to initialize {cfg.adapter} adapter. {error}"
        
        # Build prompt
        prompt, attach = await asyncio.wait_for(
            asyncio.to_thread(
                build_prompt, instructions, output_format, context, attachments, model=cfg.model_name
            ),
            timeout=5
        )
        
        # Handle vector store if supported and needed
        vs_id = vs = None
        if cfg.supports_vector_store and attach:
            vs_id = await asyncio.to_thread(create_vector_store, attach)
            vs = [vs_id] if vs_id else None
            logger.info(f"Created vector store {vs_id} for {cfg.id}")
        
        # Build parameters
        extra = dict(cfg.default_params)  # Start with defaults
        if temperature is not None:
            extra["temperature"] = temperature
        if reasoning_effort and cfg.provider == "openai":
            extra["reasoning_effort"] = reasoning_effort
        if max_reasoning_tokens and cfg.provider == "openai":
            extra["max_reasoning_tokens"] = max_reasoning_tokens
        
        # Handle session for supported models
        previous_response_id = None
        if cfg.supports_session and session_id:
            previous_response_id = session_cache.get_response_id(session_id)
            if previous_response_id:
                logger.info(f"Continuing session {session_id} with previous_response_id")
        
        try:
            # Make the API call
            result = await asyncio.wait_for(
                adapter.generate(
                    prompt, 
                    vector_store_ids=vs,
                    previous_response_id=previous_response_id,
                    timeout=cfg.default_timeout,
                    **extra
                ),
                timeout=cfg.default_timeout
            )
            
            # Handle response based on type
            if isinstance(result, dict):
                content = result.get("content", "")
                # Store response ID for next call if session provided
                if cfg.supports_session and session_id and "response_id" in result:
                    session_cache.set_response_id(session_id, result["response_id"])
                return content
            else:
                # Vertex adapter returns string directly
                return result
                
        finally:
            # Clean up vector store
            if vs_id:
                delete_vector_store(vs_id)
            logger.info(f"{cfg.id} completed in {time.time() - start_time:.2f}s")
    
    # Set function metadata
    tool_function.__name__ = cfg.id
    tool_function.__doc__ = cfg.description
    
    return tool_function

# Register all tools from configuration
for model_id, cfg in MODELS.items():
    # Register primary tool name
    tool_fn = create_tool_function(cfg)
    mcp.tool(name=cfg.id)(tool_fn)
    logger.info(f"Registered tool: {cfg.id}")
    
    # Register aliases for backward compatibility
    for alias in cfg.aliases:
        # Create a copy of the config with the alias as ID
        alias_cfg = cfg.model_copy()
        alias_cfg.id = alias
        alias_fn = create_tool_function(alias_cfg)
        mcp.tool(name=alias)(alias_fn)
        logger.info(f"Registered alias: {alias} -> {cfg.id}")

# Add vector store management tool (unchanged)
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

# Add a tool to list available models
@mcp.tool()
async def list_models() -> List[Dict[str, Any]]:
    """List all available AI models and their capabilities.
    
    Returns:
        List of model information including names, providers, and capabilities
    """
    models = []
    for cfg in MODELS.values():
        models.append({
            "id": cfg.id,
            "provider": cfg.provider,
            "model": cfg.model_name,
            "context_window": cfg.context_window,
            "timeout": cfg.default_timeout,
            "supports_session": cfg.supports_session,
            "supports_vector_store": cfg.supports_vector_store,
            "aliases": cfg.aliases,
            "description": cfg.description.strip()
        })
    return models

def main():
    """Main entry point for the MCP server."""
    logger.info(f"Starting MCP Second-Brain server with {len(MODELS)} models")
    mcp.run()

if __name__ == "__main__":
    main()
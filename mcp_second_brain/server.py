#!/usr/bin/env python3
"""MCP Second-Brain Server with dataclass-based tools."""
from mcp.server.fastmcp import FastMCP
import logging
import os
from logging.handlers import QueueHandler, QueueListener
import queue

# Import all tool definitions to register them
from .tools import definitions  # This import triggers the @tool decorators
from .tools.integration import register_all_tools, create_list_models_tool, create_vector_store_tool

# Set up logging
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

# Register all dataclass-based tools
logger.info("Registering dataclass-based tools...")
register_all_tools(mcp)

# Register utility tools
create_list_models_tool(mcp)
create_vector_store_tool(mcp)

logger.info("MCP Second-Brain server initialized with dataclass-based tools")


def main():
    """Main entry point."""
    import asyncio
    import sys
    
    # Handle --help and --version
    if "--help" in sys.argv or "-h" in sys.argv:
        print("MCP Second-Brain Server")
        print("\nUsage: mcp-second-brain")
        print("\nA Model Context Protocol server providing access to multiple AI models")
        print("with intelligent context management for large codebases.")
        print("\nOptions:")
        print("  -h, --help     Show this help message and exit")
        print("  -V, --version  Show version and exit")
        sys.exit(0)
    
    if "--version" in sys.argv or "-V" in sys.argv:
        try:
            from importlib.metadata import version
            print(version("mcp_second_brain"))
        except ImportError:
            print("0.3.2")  # Fallback version
        sys.exit(0)
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        mcp.run()
    finally:
        queue_listener.stop()


if __name__ == "__main__":
    main()
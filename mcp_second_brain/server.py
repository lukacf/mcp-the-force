#!/usr/bin/env python3
"""MCP Second-Brain Server with dataclass-based tools."""

from mcp.server.fastmcp import FastMCP
import logging
from .logging.setup import setup_logging

# Import all tool definitions to register them
from .tools import definitions  # noqa: F401 # This import triggers the @tool decorators
from .tools import search_memory  # noqa: F401 # Import search_project_memory tool
from .tools.integration import (
    register_all_tools,
    create_list_models_tool,
    create_count_project_tokens_tool,
)

# Initialize the new logging system
setup_logging()

logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("mcp-second-brain")

# Register all dataclass-based tools
logger.info("Registering dataclass-based tools...")
register_all_tools(mcp)

# Register utility tools
create_list_models_tool(mcp)
create_count_project_tokens_tool(mcp)
# Note: create_vector_store_tool is intentionally not registered to hide it from MCP clients

logger.info("MCP Second-Brain server initialized with dataclass-based tools")


def main():
    """Main entry point."""
    import asyncio
    import sys
    import signal
    import errno

    # Ignore SIGPIPE to prevent crashes on broken pipes (Unix only)
    if sys.platform != "win32":
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)

    # Handle --help and --version
    if "--help" in sys.argv or "-h" in sys.argv:
        print("MCP Second-Brain Server")
        print("\nUsage: mcp-second-brain")
        print(
            "\nA Model Context Protocol server providing access to multiple AI models"
        )
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

    while True:
        try:
            logger.info("Starting MCP server...")
            mcp.run()
            logger.info("MCP server exited normally")
            break  # Normal exit
        except KeyboardInterrupt:
            logger.info("MCP server interrupted by user")
            break  # User requested exit
        except (BrokenPipeError, OSError) as e:
            if isinstance(e, OSError) and e.errno == errno.EPIPE:  # Broken pipe errno
                logger.info("Detected broken pipe - client likely disconnected")
            else:
                logger.info(
                    f"MCP server client disconnected (pipe error: {e}) - restarting"
                )
            continue  # Restart server
        except Exception as e:
            # Handle FastMCP client disconnection errors
            import anyio

            # Check for anyio disconnection exceptions
            anyio_disconnect_errors = (
                anyio.ClosedResourceError,
                anyio.BrokenResourceError,
                anyio.EndOfStream,
            )

            # Also check for ExceptionGroup containing disconnection errors
            if isinstance(e, anyio_disconnect_errors):
                logger.info(
                    f"MCP server client disconnected ({type(e).__name__}) - restarting server"
                )
                continue  # Restart server
            elif hasattr(anyio, "ExceptionGroup") and isinstance(
                e, anyio.ExceptionGroup
            ):
                # Check if any sub-exception is a disconnection error
                if any(
                    isinstance(sub_e, anyio_disconnect_errors) for sub_e in e.exceptions
                ):
                    logger.info(
                        f"MCP server client disconnected (ExceptionGroup with {type(e).__name__}) - restarting server"
                    )
                    continue  # Restart server

            # Not a disconnection error - this is a real crash
            logger.error(f"MCP server crashed with exception: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            raise


if __name__ == "__main__":
    main()

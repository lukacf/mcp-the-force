"""
Patch MCP's stdio transport to log all communication.
"""

import json
import logging
from datetime import datetime
from typing import Any
import functools

logger = logging.getLogger(__name__)

# Create a dedicated logger for stdio messages
stdio_logger = logging.getLogger("mcp_stdio")
stdio_handler = logging.FileHandler("/Users/luka/src/cc/mcp-second-brain/mcp_stdio.log", mode='w')
stdio_handler.setFormatter(logging.Formatter('%(message)s'))
stdio_logger.addHandler(stdio_handler)
stdio_logger.setLevel(logging.INFO)
stdio_logger.propagate = False

def log_stdio_event(event_type: str, data: Any = None):
    """Log a stdio event with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    if data is None:
        stdio_logger.info(f"[{timestamp}] {event_type}")
    else:
        try:
            if isinstance(data, (dict, list)):
                formatted = json.dumps(data, indent=2)
            elif isinstance(data, bytes):
                # Try to decode as JSON
                try:
                    decoded = data.decode('utf-8')
                    parsed = json.loads(decoded)
                    formatted = json.dumps(parsed, indent=2)
                except:
                    formatted = repr(data)
            else:
                formatted = str(data)
            stdio_logger.info(f"[{timestamp}] {event_type}:\n{formatted}\n")
        except Exception as e:
            stdio_logger.info(f"[{timestamp}] {event_type} (format error: {e}):\n{repr(data)}\n")

def patch_stdio_transport():
    """Patch MCP's stdio transport to log communication."""
    try:
        import mcp.server.stdio
        
        # Patch stdin_reader
        original_stdin_reader = mcp.server.stdio.stdin_reader
        
        @functools.wraps(original_stdin_reader)
        async def stdin_reader_with_logging(read_stream_writer):
            """Wrapped stdin reader that logs messages."""
            log_stdio_event("STDIN_READER_START")
            
            # Import inside to avoid circular imports
            import sys
            from anyio import create_memory_object_stream
            from anyio.streams.file import FileReadStream
            from mcp.shared.session import InitializeRequest
            
            try:
                async for message in FileReadStream(sys.stdin.buffer):
                    log_stdio_event("STDIN_READ", message)
                    
                    # Decode and log the JSON message
                    try:
                        decoded = message.decode("utf-8") if isinstance(message, bytes) else message
                        # Remove newline and parse JSON
                        decoded = decoded.strip()
                        if decoded:
                            parsed = json.loads(decoded)
                            log_stdio_event("STDIN_PARSED", parsed)
                    except Exception as e:
                        log_stdio_event("STDIN_PARSE_ERROR", str(e))
                    
                    # Call original function logic
                    await read_stream_writer.send(InitializeRequest.model_validate(json.loads(message)))
                    
            except Exception as e:
                log_stdio_event("STDIN_READER_ERROR", f"{type(e).__name__}: {e}")
                raise
            finally:
                log_stdio_event("STDIN_READER_END")
        
        mcp.server.stdio.stdin_reader = stdin_reader_with_logging
        
        # Also try to patch the session's message sending
        try:
            from mcp.shared.session import BaseSession
            
            original_send_message = BaseSession._send_message
            
            @functools.wraps(original_send_message)
            async def send_message_with_logging(self, message: dict[str, Any]) -> None:
                """Log outgoing messages."""
                log_stdio_event("SEND_MESSAGE", message)
                return await original_send_message(self, message)
            
            BaseSession._send_message = send_message_with_logging
            
        except Exception as e:
            logger.warning(f"Could not patch session send_message: {e}")
        
        logger.info("Successfully patched stdio transport for logging")
        log_stdio_event("STDIO_LOGGING_STARTED")
        
    except Exception as e:
        logger.error(f"Failed to patch stdio transport: {e}", exc_info=True)

# Apply patch when imported
patch_stdio_transport()
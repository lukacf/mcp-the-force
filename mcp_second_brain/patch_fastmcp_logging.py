"""
Patch FastMCP to log all protocol communication for debugging.
"""

import json
import logging
import functools
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Create a separate file logger for protocol messages
protocol_logger = logging.getLogger("mcp_protocol")
protocol_handler = logging.FileHandler("/Users/luka/src/cc/mcp-second-brain/mcp_protocol.log", mode='a')
protocol_handler.setFormatter(logging.Formatter('%(message)s'))
protocol_logger.addHandler(protocol_handler)
protocol_logger.setLevel(logging.INFO)
protocol_logger.propagate = False

def log_protocol_message(direction: str, data: Any, extra: str = ""):
    """Log a protocol message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    try:
        # Pretty format if it's a dict/list
        if isinstance(data, (dict, list)):
            formatted = json.dumps(data, indent=2)
        else:
            formatted = str(data)
            
        protocol_logger.info(f"\n[{timestamp}] {direction} {extra}:\n{formatted}")
    except Exception as e:
        protocol_logger.info(f"\n[{timestamp}] {direction} {extra} (formatting error: {e}):\n{repr(data)}")

def patch_fastmcp_communication():
    """Patch FastMCP to log all communication."""
    try:
        from fastmcp import FastMCP
        
        # Patch _handle_request to log incoming requests
        original_handle_request = FastMCP._handle_request
        
        @functools.wraps(original_handle_request)
        async def _handle_request_with_logging(self, request: dict[str, Any]) -> Any:
            """Log incoming requests."""
            log_protocol_message("REQUEST", request, f"method={request.get('method', '?')}")
            
            try:
                result = await original_handle_request(self, request)
                log_protocol_message("RESPONSE", result, f"for {request.get('method', '?')}")
                return result
            except Exception as e:
                log_protocol_message("ERROR", str(e), f"handling {request.get('method', '?')}")
                raise
        
        FastMCP._handle_request = _handle_request_with_logging
        
        # Try to patch MCP session to log raw messages
        try:
            from mcp.server.session import ServerSession
            from mcp.shared.session import BaseSession
            
            # Patch _send_message to log outgoing messages
            original_send_message = BaseSession._send_message
            
            @functools.wraps(original_send_message)
            async def _send_message_with_logging(self, message: dict[str, Any]) -> None:
                """Log outgoing messages."""
                msg_type = "?"
                if "method" in message:
                    msg_type = f"notification:{message['method']}"
                elif "result" in message:
                    msg_type = "result"
                elif "error" in message:
                    msg_type = "error"
                    
                log_protocol_message("SEND", message, msg_type)
                return await original_send_message(self, message)
            
            BaseSession._send_message = _send_message_with_logging
            
            # Patch message receiving
            original_receive_loop = BaseSession._receive_loop
            
            @functools.wraps(original_receive_loop)
            async def _receive_loop_with_logging(self) -> None:
                """Wrap receive loop to log incoming messages."""
                # Get the original _handle_message method
                original_handle_message = self._handle_message
                
                async def _handle_message_with_logging(message: dict[str, Any]) -> None:
                    """Log received messages."""
                    msg_type = "?"
                    if "method" in message:
                        if "id" in message:
                            msg_type = f"request:{message['method']}"
                        else:
                            msg_type = f"notification:{message['method']}"
                    elif "result" in message:
                        msg_type = "result"
                    elif "error" in message:
                        msg_type = "error"
                        
                    log_protocol_message("RECV", message, msg_type)
                    return await original_handle_message(message)
                
                # Temporarily replace _handle_message
                self._handle_message = _handle_message_with_logging
                try:
                    return await original_receive_loop(self)
                finally:
                    self._handle_message = original_handle_message
            
            BaseSession._receive_loop = _receive_loop_with_logging
            
            logger.info("Successfully patched MCP session for protocol logging")
            
        except Exception as e:
            logger.warning(f"Could not patch MCP session: {e}")
        
        logger.info("Successfully patched FastMCP for protocol logging")
        protocol_logger.info(f"\n{'='*60}\nPROTOCOL LOGGING STARTED AT {datetime.now()}\n{'='*60}")
        
    except Exception as e:
        logger.error(f"Failed to patch FastMCP for logging: {e}")

# Apply patch when imported
patch_fastmcp_communication()
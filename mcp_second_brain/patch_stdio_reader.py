"""
Patch MCP's stdio_server to handle client disconnections gracefully.
This prevents BrokenResourceError from crashing the server when clients abort.
"""

import sys
import logging
from contextlib import asynccontextmanager
from io import TextIOWrapper

import anyio
import anyio.lowlevel
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

import mcp.server.stdio
import mcp.types as types
from mcp.shared.message import SessionMessage

logger = logging.getLogger(__name__)

# Store the original stdio_server
_original_stdio_server = None


@asynccontextmanager
async def patched_stdio_server(
    stdin: anyio.AsyncFile[str] | None = None,
    stdout: anyio.AsyncFile[str] | None = None,
):
    """
    Patched stdio_server that handles session disconnections gracefully.
    The server survives when the session dies but stdin is still open.
    """
    # Purposely not using context managers for these, as we don't want to close
    # standard process handles. Encoding of stdin/stdout as text streams on
    # python is platform-dependent (Windows is particularly problematic), so we
    # re-wrap the underlying binary stream to ensure UTF-8.
    if not stdin:
        stdin = anyio.wrap_file(TextIOWrapper(sys.stdin.buffer, encoding="utf-8"))
    if not stdout:
        stdout = anyio.wrap_file(TextIOWrapper(sys.stdout.buffer, encoding="utf-8"))

    read_stream: MemoryObjectReceiveStream[SessionMessage | Exception]
    read_stream_writer: MemoryObjectSendStream[SessionMessage | Exception]

    write_stream: MemoryObjectSendStream[SessionMessage]
    write_stream_reader: MemoryObjectReceiveStream[SessionMessage]

    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

    async def stdin_reader():
        try:
            async with read_stream_writer:
                async for line in stdin:
                    try:
                        message = types.JSONRPCMessage.model_validate_json(line)
                        session_message = SessionMessage(message)
                        await read_stream_writer.send(session_message)
                    except anyio.BrokenResourceError:
                        # This is the key change. The session's read-end of the
                        # stream is gone, but stdin may still be open.
                        # We log it, drop the message, and continue the loop
                        # to wait for stdin to properly close.
                        logger.warning("Session stream was closed. Message dropped.")
                        continue  # <- THIS IS THE FIX
                    except Exception as exc:
                        # This can also fail if the session is gone, so wrap it
                        try:
                            await read_stream_writer.send(exc)
                        except anyio.BrokenResourceError:
                            logger.warning("Session stream closed while sending validation error. Message dropped.")
                        continue

        except anyio.ClosedResourceError:
            # This is a clean exit, stdin itself was closed.
            await anyio.lowlevel.checkpoint()

    async def stdout_writer():
        try:
            async with write_stream_reader:
                async for session_message in write_stream_reader:
                    json = session_message.message.model_dump_json(by_alias=True, exclude_none=True)
                    await stdout.write(json + "\n")
                    await stdout.flush()
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()

    async with anyio.create_task_group() as tg:
        tg.start_soon(stdin_reader)
        tg.start_soon(stdout_writer)
        yield read_stream, write_stream


def apply_patch():
    """Apply the patch to MCP's stdio_server."""
    global _original_stdio_server
    
    # Save the original function
    _original_stdio_server = mcp.server.stdio.stdio_server
    
    # Replace with our patched version
    mcp.server.stdio.stdio_server = patched_stdio_server
    
    logger.info("Applied stdio server patch to handle session disconnections gracefully")


# Apply the patch when this module is imported
apply_patch()
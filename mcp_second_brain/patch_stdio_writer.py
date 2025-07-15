"""
Patch the ONE place where MCP writes to stdout to handle ALL disconnect errors.
Import BEFORE any MCP imports.
"""

import logging
import os
import datetime
from mcp.server import stdio

_LOG = logging.getLogger(__name__)

def _dbg(msg: str):
    try:
        with open(os.path.join(os.getcwd(), "mcp_cancellation_debug.log"), "a") as f:
            f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S.%f}] STDIO_PATCH: {msg}\n")
    except Exception:
        pass

# Store original function
_original_stdio_server = stdio.stdio_server

# Create patched version
from contextlib import asynccontextmanager
import anyio
import anyio.lowlevel
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
import mcp.types as types
from mcp.shared.message import SessionMessage
import sys
from io import TextIOWrapper

@asynccontextmanager
async def patched_stdio_server(
    stdin: anyio.AsyncFile[str] | None = None,
    stdout: anyio.AsyncFile[str] | None = None,
):
    """Patched stdio_server that handles ALL write errors gracefully."""
    # Copy the original setup code
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
                    except Exception as exc:
                        await read_stream_writer.send(exc)
                        continue
                    session_message = SessionMessage(message)
                    await read_stream_writer.send(session_message)
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()

    async def stdout_writer():
        """THE ONE PLACE that writes to stdout - now handles ALL disconnect errors."""
        try:
            async with write_stream_reader:
                async for session_message in write_stream_reader:
                    try:
                        json = session_message.message.model_dump_json(by_alias=True, exclude_none=True)
                        await stdout.write(json + "\n")
                        await stdout.flush()
                    except (
                        anyio.BrokenResourceError,
                        anyio.ClosedResourceError, 
                        anyio.EndOfStream,
                        BrokenPipeError,
                        ConnectionResetError,
                        OSError,  # Catches EPIPE and other OS-level errors
                    ) as e:
                        _LOG.debug("Client disconnected during stdout write: %s", e)
                        _dbg(f"Swallowed {type(e).__name__} in stdout_writer: {e}")
                        # Stop trying to write once client is gone
                        break
        except (anyio.ClosedResourceError, anyio.BrokenResourceError) as e:
            _dbg(f"stdout_writer task ending: {type(e).__name__}")
            await anyio.lowlevel.checkpoint()

    async with anyio.create_task_group() as tg:
        tg.start_soon(stdin_reader)
        tg.start_soon(stdout_writer)
        yield read_stream, write_stream

# Replace the function
stdio.stdio_server = patched_stdio_server
_dbg("Patched stdio.stdio_server - THE one place that writes to stdout")
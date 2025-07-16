#!/usr/bin/env python3
"""
Stdio interceptor for debugging MCP communication.
Sits between Claude and MCP server, logging all communication.
"""

import sys
import asyncio
import json
import time
import subprocess
from datetime import datetime
import os

# Log file for intercepted messages
LOG_FILE = "/Users/luka/src/cc/mcp-second-brain/stdio_intercept.log"

def log_message(direction, data, is_json=False):
    """Log a message with timestamp and direction."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    with open(LOG_FILE, "a") as f:
        if is_json:
            try:
                # Pretty print JSON for readability
                parsed = json.loads(data)
                formatted = json.dumps(parsed, indent=2)
                f.write(f"\n[{timestamp}] {direction}:\n{formatted}\n")
            except:
                # If not valid JSON, log as-is
                f.write(f"\n[{timestamp}] {direction}: {repr(data)}\n")
        else:
            f.write(f"\n[{timestamp}] {direction}: {repr(data)}\n")
        f.flush()

async def pipe_with_logging(reader, writer, direction, other_writer=None):
    """Pipe data from reader to writer, logging everything."""
    buffer = ""
    
    try:
        while True:
            # Read a chunk
            chunk = await reader.read(4096)
            if not chunk:
                log_message(f"{direction}_EOF", "End of stream")
                if other_writer:
                    other_writer.close()
                break
            
            # Log raw chunk
            chunk_str = chunk.decode('utf-8', errors='replace')
            log_message(f"{direction}_RAW", chunk_str, is_json=False)
            
            # Write through immediately (if writer provided)
            if writer:
                writer.write(chunk)
                await writer.drain()
            
            # Try to extract complete JSON messages
            buffer += chunk_str
            
            # Look for complete JSON messages (naive approach)
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if line.strip():
                    log_message(f"{direction}_JSON", line, is_json=True)
                    
    except asyncio.CancelledError:
        log_message(f"{direction}_CANCELLED", "Pipe cancelled")
        raise
    except Exception as e:
        log_message(f"{direction}_ERROR", f"Error: {type(e).__name__}: {e}")
        raise

async def main():
    """Run the stdio interceptor."""
    # Clear previous log
    with open(LOG_FILE, "w") as f:
        f.write(f"=== STDIO INTERCEPTOR STARTED AT {datetime.now()} ===\n")
    
    log_message("STARTUP", f"Arguments: {sys.argv}")
    
    # Start the actual MCP server as subprocess
    server_cmd = [sys.executable, "-m", "mcp_second_brain.server"]
    
    proc = await asyncio.create_subprocess_exec(
        *server_cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    log_message("SUBPROCESS", f"Started MCP server with PID {proc.pid}")
    
    # Create async streams for stdin/stdout
    loop = asyncio.get_event_loop()
    stdin_reader = asyncio.StreamReader()
    stdin_protocol = asyncio.StreamReaderProtocol(stdin_reader)
    await loop.connect_read_pipe(lambda: stdin_protocol, sys.stdin.buffer)
    
    stdout_writer = asyncio.StreamWriter(
        transport=None,
        protocol=None,
        reader=None,
        loop=loop
    )
    stdout_writer._transport = await loop.connect_write_pipe(
        lambda: asyncio.Protocol(), sys.stdout.buffer
    )
    
    # Set up bidirectional piping with logging
    tasks = [
        # Claude -> Server
        asyncio.create_task(
            pipe_with_logging(stdin_reader, proc.stdin, "CLAUDE->SERVER", proc.stdin)
        ),
        # Server -> Claude  
        asyncio.create_task(
            pipe_with_logging(proc.stdout, stdout_writer, "SERVER->CLAUDE")
        ),
        # Server stderr logging
        asyncio.create_task(
            pipe_with_logging(proc.stderr, None, "SERVER_STDERR")
        ),
    ]
    
    try:
        # Wait for any task to complete
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        
        log_message("SHUTDOWN", f"Task completed: {done}")
        
        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            
    except KeyboardInterrupt:
        log_message("SHUTDOWN", "Keyboard interrupt")
    except Exception as e:
        log_message("ERROR", f"Main loop error: {type(e).__name__}: {e}")
    finally:
        # Kill the subprocess
        if proc.returncode is None:
            proc.terminate()
            await asyncio.sleep(0.5)
            if proc.returncode is None:
                proc.kill()
                
        log_message("EXIT", f"Subprocess exit code: {proc.returncode}")

if __name__ == "__main__":
    asyncio.run(main())
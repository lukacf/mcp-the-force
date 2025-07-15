#!/usr/bin/env python3
"""
Test if the crash happens when the background operation completes.
Monitor the server for a longer period to catch the delayed crash.
"""

import asyncio
import json
import sys
import os
import time
from datetime import datetime

async def test_delayed_crash():
    """Monitor for delayed crash after abort."""
    
    print("=== Testing for Delayed Crash After Abort ===")
    
    # Start MCP server
    cmd = [sys.executable, "-m", "mcp_second_brain.server"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.getcwd()
    )
    
    print(f"Started MCP server with PID {proc.pid}")
    
    # Monitor stderr for crashes
    crash_detected = False
    async def stderr_monitor():
        nonlocal crash_detected
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            msg = line.decode().rstrip()
            if msg and not msg.startswith(('╭', '│', '╰')):
                print(f"[STDERR] {msg}")
                if any(x in msg.lower() for x in ['error', 'exception', 'traceback', 'crashed']):
                    crash_detected = True
    
    stderr_task = asyncio.create_task(stderr_monitor())
    
    try:
        # Initialize
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Initializing...")
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0.0"}
            },
            "id": 1
        }
        
        proc.stdin.write((json.dumps(init_request) + "\n").encode())
        await proc.stdin.drain()
        
        response = await proc.stdout.readline()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Initialized")
        
        # Send initialized notification
        proc.stdin.write((json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }) + "\n").encode())
        await proc.stdin.drain()
        
        await asyncio.sleep(0.5)
        
        # Make a SHORT o3 call that will complete soon
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Making SHORT o3 call...")
        tool_call = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "chat_with_o3",
                "arguments": {
                    "instructions": "Just say 'Hello World'",  # Very short task
                    "output_format": "Plain text",
                    "context": [],
                    "session_id": "crash-test",
                    "reasoning_effort": "low"  # Minimal reasoning
                }
            },
            "id": 2
        }
        
        proc.stdin.write((json.dumps(tool_call) + "\n").encode())
        await proc.stdin.drain()
        
        # Read responses briefly
        response_task = asyncio.create_task(proc.stdout.readline())
        
        # Abort quickly (after 5 seconds)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting 5 seconds before abort...")
        await asyncio.sleep(5)
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] === ABORTING ===")
        response_task.cancel()
        try:
            await response_task
        except asyncio.CancelledError:
            pass
        
        # Keep stdin open but stop reading stdout
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Stopped reading stdout (but stdin still open)")
        
        # Now monitor for crash when operation completes
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Monitoring for delayed crash...")
        print("(The o3 operation should complete soon and try to send response)")
        
        start_monitor = time.time()
        while time.time() - start_monitor < 60:  # Monitor for up to 60 seconds
            # Send periodic pings to check if server is alive
            if int(time.time() - start_monitor) % 10 == 0:
                ping = {
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": int(time.time())
                }
                
                try:
                    proc.stdin.write((json.dumps(ping) + "\n").encode())
                    await proc.stdin.drain()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Ping sent (server still accepting commands)")
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Failed to send ping: {e}")
                    break
            
            # Check if process crashed
            if proc.returncode is not None:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] *** SERVER CRASHED! Exit code: {proc.returncode} ***")
                break
            
            if crash_detected:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] *** CRASH DETECTED IN STDERR! ***")
                await asyncio.sleep(2)  # Give it time to fully crash
                break
            
            await asyncio.sleep(1)
        
        # Final status
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Final status:")
        if proc.returncode is None:
            print(f"  Server still running (PID {proc.pid})")
        else:
            print(f"  Server exited with code {proc.returncode}")
        
        # Check debug log
        if os.path.exists("mcp_cancellation_debug.log"):
            print("\n=== Debug Log (last 30 lines) ===")
            with open("mcp_cancellation_debug.log", "r") as f:
                lines = f.readlines()
                for line in lines[-30:]:
                    print(line.rstrip())
        
    finally:
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()
        
        stderr_task.cancel()
        try:
            await stderr_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    # Clear logs
    for f in ["mcp_cancellation_debug.log", "mcp_debug_trace.log"]:
        if os.path.exists(f):
            os.remove(f)
    
    asyncio.run(test_delayed_crash())
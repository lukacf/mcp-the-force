#!/usr/bin/env python3
"""
Test more aggressive abort scenarios that might match Claude's behavior.
"""

import asyncio
import json
import sys
import os
import signal
from datetime import datetime


async def test_aggressive_abort():
    """Test various aggressive abort methods."""

    print("=== Testing Aggressive Abort Scenarios ===")

    # Test different abort methods
    abort_methods = [
        "close_stdin_only",
        "close_both_stdin_stdout",
        "send_sigterm",
        "send_sigint",
        "close_and_sigterm",
    ]

    for method in abort_methods:
        print(f"\n{'='*60}")
        print(f"Testing abort method: {method}")
        print("=" * 60)

        # Clear logs
        for f in ["mcp_cancellation_debug.log"]:
            if os.path.exists(f):
                os.remove(f)

        # Start server
        cmd = [sys.executable, "-m", "mcp_second_brain.server"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd(),
        )

        print(f"Started server PID {proc.pid}")

        # Capture stderr
        stderr_lines = []

        async def stderr_reader():
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                stderr_lines.append(line.decode())

        stderr_task = asyncio.create_task(stderr_reader())

        try:
            # Initialize
            init = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
                "id": 1,
            }

            proc.stdin.write((json.dumps(init) + "\n").encode())
            await proc.stdin.drain()
            await proc.stdout.readline()

            # Send initialized
            proc.stdin.write(
                (
                    json.dumps(
                        {"jsonrpc": "2.0", "method": "notifications/initialized"}
                    )
                    + "\n"
                ).encode()
            )
            await proc.stdin.drain()

            await asyncio.sleep(0.5)

            # Make o3 call
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Making o3 call...")
            call = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "chat_with_o3",
                    "arguments": {
                        "instructions": "Count to 5",
                        "output_format": "Simple",
                        "context": [],
                        "session_id": f"abort-{method}",
                    },
                },
                "id": 2,
            }

            proc.stdin.write((json.dumps(call) + "\n").encode())
            await proc.stdin.drain()

            # Wait 14 seconds
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting 14 seconds...")
            await asyncio.sleep(14)

            # ABORT using different methods
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] Aborting with method: {method}"
            )

            if method == "close_stdin_only":
                proc.stdin.close()

            elif method == "close_both_stdin_stdout":
                proc.stdin.close()
                if proc.stdout:
                    proc.stdout._transport.close()  # Force close stdout transport

            elif method == "send_sigterm":
                os.kill(proc.pid, signal.SIGTERM)

            elif method == "send_sigint":
                os.kill(proc.pid, signal.SIGINT)

            elif method == "close_and_sigterm":
                proc.stdin.close()
                await asyncio.sleep(0.1)
                os.kill(proc.pid, signal.SIGTERM)

            # Monitor result
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Monitoring...")

            # Wait for exit or timeout
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Server exited with code: {proc.returncode}"
                )
            except asyncio.TimeoutError:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] Server still running after 10s"
                )
                proc.terminate()
                await proc.wait()

            # Check for errors in stderr
            error_found = False
            for line in stderr_lines:
                if any(
                    x in line.lower()
                    for x in ["error", "exception", "traceback", "assert"]
                ):
                    if not error_found:
                        print("\n*** ERRORS DETECTED ***")
                        error_found = True
                    print(line.rstrip())

            # Check debug log
            if os.path.exists("mcp_cancellation_debug.log"):
                with open("mcp_cancellation_debug.log", "r") as f:
                    content = f.read()
                    if "already responded" in content:
                        print("\n*** FOUND 'already responded' ERROR IN DEBUG LOG ***")
                    if "ExceptionGroup" in content:
                        print("\n*** FOUND ExceptionGroup IN DEBUG LOG ***")
                        # Show relevant lines
                        for line in content.split("\n"):
                            if any(
                                x in line
                                for x in ["ExceptionGroup", "CANCEL", "already"]
                            ):
                                print(line)

        finally:
            if proc.returncode is None:
                proc.terminate()
                await proc.wait()

            stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass

        print(f"\nMethod '{method}' completed")
        await asyncio.sleep(2)  # Brief pause between tests


if __name__ == "__main__":
    asyncio.run(test_aggressive_abort())

#!/usr/bin/env python3
"""
Comprehensive monitoring of MCP abort behavior.
This captures all signals, logs, and timing information.
"""

import asyncio
import json
import sys
import os
import time
import threading
from datetime import datetime
from collections import defaultdict


class AbortMonitor:
    def __init__(self):
        self.events = []
        self.start_time = time.time()

    def log_event(self, event_type, message, extra=None):
        """Log an event with timestamp."""
        elapsed = time.time() - self.start_time
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        event = {
            "timestamp": timestamp,
            "elapsed": elapsed,
            "type": event_type,
            "message": message,
        }
        if extra:
            event["extra"] = extra
        self.events.append(event)

        # Print colored output based on type
        color = {
            "START": "\033[92m",  # Green
            "ABORT": "\033[91m",  # Red
            "SERVER": "\033[94m",  # Blue
            "RESPONSE": "\033[93m",  # Yellow
            "ERROR": "\033[91m",  # Red
            "DEBUG": "\033[95m",  # Magenta
        }.get(event_type, "")

        print(f"{color}[{timestamp}] +{elapsed:6.2f}s {event_type}: {message}\033[0m")

    def monitor_file(self, filepath, label):
        """Monitor a file for changes in a background thread."""

        def _monitor():
            last_size = 0
            while True:
                try:
                    if os.path.exists(filepath):
                        current_size = os.path.getsize(filepath)
                        if current_size > last_size:
                            with open(filepath, "r") as f:
                                f.seek(last_size)
                                new_content = f.read()
                                if new_content.strip():
                                    self.log_event(
                                        "DEBUG", f"{label}: {new_content.strip()[:200]}"
                                    )
                            last_size = current_size
                except Exception:
                    pass
                time.sleep(0.1)

        thread = threading.Thread(target=_monitor, daemon=True)
        thread.start()
        return thread


async def run_abort_test():
    """Run comprehensive abort test."""
    monitor = AbortMonitor()

    # Start monitoring debug files
    monitor.monitor_file("mcp_cancellation_debug.log", "CancelDebug")
    monitor.monitor_file("mcp_debug_trace.log", "TraceDebug")

    monitor.log_event("START", "Starting MCP server subprocess")

    # Start MCP server
    cmd = [sys.executable, "-m", "mcp_second_brain.server"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.getcwd(),
    )

    monitor.log_event("START", f"Server started with PID {proc.pid}")

    # Monitor stderr
    async def stderr_monitor():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            msg = line.decode().rstrip()
            if msg and not msg.startswith("╭") and not msg.startswith("│"):
                monitor.log_event("SERVER", f"stderr: {msg}")

    stderr_task = asyncio.create_task(stderr_monitor())

    try:
        # Initialize
        monitor.log_event("START", "Sending initialize request")
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
                "clientInfo": {"name": "abort-monitor", "version": "1.0.0"},
            },
            "id": 1,
        }

        proc.stdin.write((json.dumps(init_request) + "\n").encode())
        await proc.stdin.drain()

        # Read initialization response
        response = await proc.stdout.readline()
        monitor.log_event("RESPONSE", "Got initialization response")

        # Send initialized
        monitor.log_event("START", "Sending initialized notification")
        proc.stdin.write(
            (
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
                + "\n"
            ).encode()
        )
        await proc.stdin.drain()

        await asyncio.sleep(0.5)

        # Make o3 call
        monitor.log_event("START", "Making o3 tool call")
        tool_call = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "chat_with_o3",
                "arguments": {
                    "instructions": "Analyze the halting problem and its implications for computer science",
                    "output_format": "Technical analysis",
                    "context": [],
                    "session_id": f"monitor-{int(time.time())}",
                    "reasoning_effort": "high",
                },
            },
            "id": 2,
        }

        proc.stdin.write((json.dumps(tool_call) + "\n").encode())
        await proc.stdin.drain()

        # Monitor responses
        response_task = None

        async def response_monitor():
            try:
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        monitor.log_event("RESPONSE", "stdout closed")
                        break
                    monitor.log_event("RESPONSE", f"Got: {line.decode().strip()[:100]}")
            except asyncio.CancelledError:
                monitor.log_event("RESPONSE", "Response monitor cancelled")
                raise

        response_task = asyncio.create_task(response_monitor())

        # Wait exactly 14 seconds
        monitor.log_event("START", "Waiting 14 seconds before abort...")
        await asyncio.sleep(14)

        # ABORT
        monitor.log_event("ABORT", "SIMULATING USER ABORT NOW")
        monitor.log_event("ABORT", "Cancelling response reader")
        response_task.cancel()

        monitor.log_event("ABORT", "Closing stdin")
        proc.stdin.close()

        monitor.log_event("ABORT", "Connection abandoned - monitoring server")

        # Monitor for 30 seconds
        for i in range(30):
            await asyncio.sleep(1)
            if proc.returncode is not None:
                monitor.log_event(
                    "SERVER", f"Process exited with code {proc.returncode}"
                )
                break
            else:
                if i % 5 == 0:
                    monitor.log_event("SERVER", f"Still running (PID {proc.pid})")

    finally:
        # Print summary
        print("\n" + "=" * 80)
        print("ABORT TEST SUMMARY")
        print("=" * 80)

        # Group events by type
        by_type = defaultdict(list)
        for event in monitor.events:
            by_type[event["type"]].append(event)

        # Key timings
        abort_time = next(
            (e["elapsed"] for e in monitor.events if e["type"] == "ABORT"), None
        )
        exit_time = next(
            (e["elapsed"] for e in monitor.events if "exited" in e["message"]), None
        )

        print("\nKey Timings:")
        print(f"  Abort at: {abort_time:.2f}s")
        if exit_time:
            print(f"  Exit at: {exit_time:.2f}s")
            print(f"  Survival time: {exit_time - abort_time:.2f}s")
        else:
            print(f"  Server still running after {monitor.events[-1]['elapsed']:.2f}s")

        # Cancellation events
        print("\nCancellation Events:")
        cancel_events = [e for e in monitor.events if "cancel" in e["message"].lower()]
        for e in cancel_events:
            print(f"  +{e['elapsed']:6.2f}s: {e['message']}")

        # Cleanup
        if proc.returncode is None:
            proc.terminate()
            await proc.wait()

        stderr_task.cancel()
        try:
            await stderr_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    # Clean logs
    for f in ["mcp_cancellation_debug.log", "mcp_debug_trace.log"]:
        if os.path.exists(f):
            os.remove(f)

    asyncio.run(run_abort_test())

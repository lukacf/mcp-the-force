#!/usr/bin/env python3
"""
Run the MCP server with detailed execution tracing.
This will help us understand what happens during cancellation.
"""

import sys
import os
import trace
import threading
import time

# Add the project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Create a trace object
tracer = trace.Trace(
    count=0,  # Don't count execution
    trace=1,  # Trace execution
    countfuncs=0,  # Don't count functions
    countcallers=0,  # Don't count callers
    ignoremods=(),  # Don't ignore any modules
    ignoredirs=(  # Ignore standard library
        sys.prefix,
        sys.exec_prefix,
    ),
    infile=None,
    outfile=None,
    timing=True,  # Show timing info
)

# Import after trace is set up


def monitor_trace_file():
    """Monitor the trace output file for cancellation-related events."""
    trace_file = "mcp_trace.log"
    keywords = ["cancel", "Cancel", "abort", "disconnect", "broken", "error"]

    print(f"Monitoring {trace_file} for keywords: {keywords}")

    while True:
        time.sleep(1)
        try:
            with open(trace_file, "r") as f:
                lines = f.readlines()
                for line in lines[-100:]:  # Check last 100 lines
                    if any(keyword in line for keyword in keywords):
                        print(f"TRACE MATCH: {line.strip()}")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Monitor error: {e}")


if __name__ == "__main__":
    # Start the trace monitor in a background thread
    monitor_thread = threading.Thread(target=monitor_trace_file, daemon=True)
    monitor_thread.start()

    # Open a file for trace output
    with open("mcp_trace.log", "w") as trace_out:
        sys.stdout = trace_out
        sys.stderr = trace_out

        # Run the server with tracing
        print("Starting MCP server with tracing enabled...")
        tracer.run("main()")

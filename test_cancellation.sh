#!/bin/bash
# Test cancellation behavior with comprehensive tracing

echo "=== MCP Cancellation Test Suite ==="
echo "This will help us understand what happens when Claude Code aborts"
echo

# Clean up old logs
rm -f cancellation_trace.log mcp_cancellation_debug.log

# Start the trace viewer in background
echo "Starting trace viewer..."
python view_trace.py &
VIEWER_PID=$!

# Give viewer time to start
sleep 1

# Run the abort simulation
echo
echo "Running abort simulation..."
python simulate_claude_abort.py

# Kill the viewer
kill $VIEWER_PID 2>/dev/null

# Show the trace summary
echo
echo "=== Trace Summary ==="
echo "Key events from cancellation_trace.log:"
echo

if [ -f cancellation_trace.log ]; then
    grep -E "(CANCEL|TIMEOUT|ERROR|CANCELLED)" cancellation_trace.log | tail -20
else
    echo "No trace file found!"
fi

echo
echo "=== Debug Log Summary ==="
if [ -f mcp_cancellation_debug.log ]; then
    echo "Last 10 lines from mcp_cancellation_debug.log:"
    tail -10 mcp_cancellation_debug.log
else
    echo "No debug log found!"
fi
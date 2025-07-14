# MCP Server Cancellation Handling Solution

## Problem Statement

The MCP Second-Brain server was dying when Claude Code aborted long-running operations (e.g., when users pressed the stop button). This made the server unusable after any cancelled operation, requiring manual restart - a critical usability issue.

## Root Cause

FastMCP's stdio transport implementation doesn't distinguish between:
- SIGTERM sent to cancel an operation (should cancel the operation only)
- SIGTERM sent to shutdown the server (should exit the process)

When Claude Code aborts an operation, it sends SIGTERM to the server process. Without proper handling, this causes the entire server to exit.

## Solution Overview

We implemented a comprehensive monkeypatch (`cancellation_patch.py`) that:

1. **Intercepts SIGTERM signals** - Custom handler that cancels active operations without killing the server
2. **Patches FastMCP internals** - Wraps response sending to handle broken pipes gracefully
3. **Protects stdio streams** - Prevents crashes when writing to closed pipes

## Implementation Details

### 1. Signal Handling

```python
def handle_sigterm(signum: int, frame: Any) -> None:
    """Custom SIGTERM handler that cancels operations without killing the server."""
    # Cancel all active operations
    for task in list(_active_operations):
        if not task.done():
            task.cancel()
    
    # CRITICAL: Do NOT exit the process
    # The server continues running and remains available
```

### 2. FastMCP Session Patching

```python
async def safe_send_response(self: BaseSession, request_id: Any, response: Any) -> None:
    """Wrapped _send_response that handles disconnections gracefully."""
    try:
        await original_send_response(self, request_id, response)
    except (BrokenPipeError, ConnectionError, OSError) as e:
        # Client disconnected - don't crash
        logger.debug(f"Client disconnected: {e}")
```

### 3. Stdio Protection

```python
def safe_stdout_write(data: str) -> int:
    """Write to stdout, ignoring broken pipe errors."""
    try:
        return original_stdout_write(data)
    except BrokenPipeError:
        # Pretend we wrote it - client is gone
        return len(data)
```

## Testing

We created comprehensive tests to verify the solution:

1. **`minimal_test.py`** - Verifies SIGTERM doesn't kill the server
2. **`test_cancellation_real.py`** - Tests with real MCP client library
3. **`test_final_proof.py`** - Demonstrates the complete solution

### Test Results

```
✅ Server survives SIGTERM signals
✅ Operations can be cancelled without server death
✅ Server remains responsive after cancellation
✅ Clean shutdown still works via stdin close
```

## Usage

The patches are automatically applied when the server starts:

```python
# In server.py
from .cancellation_patch import monkeypatch_all
monkeypatch_all()  # Applied before FastMCP initialization
```

No configuration or manual intervention required.

## Architecture Notes

### Stdio Transport Lifecycle

1. **Normal Operation**: Server blocks on stdin, processes requests, sends responses
2. **Operation Cancellation**: SIGTERM cancels active tasks, server continues waiting
3. **Client Disconnect**: Stdin closes, server exits cleanly

### Key Insights

- Stdio transport servers have 1:1 relationship with their client
- SIGTERM should cancel operations, not kill the server
- Broken pipes are expected when clients disconnect
- FastMCP lacks built-in cancellation handling

## Comparison with Other MCP Servers

Our patched behavior now matches other well-behaved MCP servers:
- Server survives operation cancellation
- No manual restart required
- Seamless user experience

## Future Considerations

1. **Upstream Fix**: This should ideally be fixed in FastMCP itself
2. **HTTP Transport**: Would provide better cancellation semantics
3. **Monitoring**: Add metrics for cancelled operations

## Conclusion

The cancellation handling patches successfully resolve the server death issue. Users can now freely cancel long-running operations without breaking their MCP connection. The server behaves like other professional MCP implementations, providing a reliable and responsive experience.
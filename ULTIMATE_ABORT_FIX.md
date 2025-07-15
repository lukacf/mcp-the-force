# The Ultimate MCP Abort Fix - Understanding the Full Stack

## The Complete Problem

When Claude Code aborts an operation:
1. It sends `notifications/cancelled` to the MCP server
2. The MCP library (`mcp/shared/session.py`) handles this by:
   - Calling `_cancel_scope.cancel()` → triggers CancelledError
   - Setting `_completed = True` to mark request as handled
   - **Sending an error response: "Request cancelled"**
3. If our code re-raises CancelledError, FastMCP tries to send ANOTHER response
4. This causes "AssertionError: Request already responded to"

## The Solution

Handle cancellation at the OperationManager level and return a sentinel value instead of propagating the exception. This prevents FastMCP from trying to send a second response.

### Changes Made

#### 1. OperationManager (operation_manager.py)
```python
# Added sentinel class
class CancellationSentinel:
    pass
CANCELLED = CancellationSentinel()

# Modified run_with_timeout to return sentinel
except asyncio.CancelledError:
    logger.info(f"Operation {operation_id} was cancelled by MCP. Returning sentinel.")
    if not task.done():
        task.cancel()
    return CANCELLED  # Instead of raise
```

#### 2. ToolExecutor (executor.py)
```python
# Import the sentinel
from ..operation_manager import operation_manager, CANCELLED

# Check for sentinel after run_with_timeout
if result is CANCELLED:
    logger.info(f"Tool '{tool_id}' was cancelled by MCP. Returning empty string.")
    was_cancelled = True
    return ""

# Removed all CancelledError handlers - no longer needed
```

#### 3. OpenAI Adapter (flow.py)
Already fixed to re-raise CancelledError instead of swallowing it.

## How It Works

1. User aborts → MCP receives `notifications/cancelled`
2. MCP cancels the scope and sends "Request cancelled" response
3. CancelledError propagates through OpenAI adapter
4. OperationManager catches it and returns CANCELLED sentinel
5. ToolExecutor sees sentinel and returns empty string
6. FastMCP does NOT send another response (request already handled by MCP)
7. No double response → No AssertionError → Server stays alive

## Key Insights

- MCP library handles cancellation responses at a lower level than FastMCP expects
- We must prevent exception propagation to avoid triggering FastMCP's error handling
- The sentinel pattern allows clean communication without exceptions
- Empty string return prevents FastMCP from sending any response

This solution properly respects the MCP protocol's cancellation handling while preventing race conditions in the response system.
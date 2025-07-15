# Final MCP Abort Fix - Race Condition TRULY Resolved

## The Real Root Cause (Found by Gemini 2.5 Pro)
The OpenAI adapter was swallowing `CancelledError` instead of re-raising it, breaking the entire cancellation chain:

1. User aborts → CancelledError raised in polling loop
2. OpenAI adapter catches it but returns `{"content": "", "response_id": "cancelled"}` instead of re-raising
3. OperationManager sees normal completion, not cancellation  
4. ToolExecutor never enters its CancelledError handler
5. System sends first response thinking operation succeeded
6. 10-80 seconds later, OpenAI job completes and triggers internal callbacks
7. FastMCP detects attempt to respond to already-responded request → AssertionError

## The Solution
Fix the OpenAI adapter to properly propagate cancellation.

### The Critical Fix

Changed one line in `/mcp_second_brain/adapters/openai/flow.py`:

```python
# Before (WRONG - swallows the error):
except asyncio.CancelledError:
    logger.info(f"Polling cancelled for {response_id}")
    return {"content": "", "response_id": "cancelled"}

# After (CORRECT - propagates cancellation):
except asyncio.CancelledError:
    logger.info(f"Polling cancelled for {response_id}")
    raise
```

### Supporting Changes

1. **Removed patch_fastmcp_cancel import** (server.py) - Was causing double response attempts
2. **Enhanced ToolExecutor** (executor.py) - Now properly handles CancelledError
3. **Safe memory wrapper** (safe_memory.py) - Prevents background tasks from interfering

## How It Works Now

1. User presses Escape → Claude Code closes the pipe
2. Python detects broken pipe → raises CancelledError  
3. OpenAI adapter re-raises CancelledError (FIXED!)
4. OperationManager detects cancellation and re-raises
5. ToolExecutor catches CancelledError → returns empty string
6. FastMCP sends ONE success response with empty result
7. System correctly marked as cancelled, no lingering state
8. No race condition when OpenAI job eventually completes

## Testing Instructions

1. Start the server normally:
   ```bash
   uv run -- mcp-second-brain
   ```

2. In Claude Code, run a long o3/o3-pro query

3. Press Escape after a few seconds

4. The server should remain connected without any "Request already responded to" errors

## Key Insight
The fix works by ensuring that only ONE layer (ToolExecutor) handles the cancellation and determines what response to send. By returning an empty string, we tell FastMCP "this succeeded with no output" which is exactly what Claude Code expects when the user aborts.
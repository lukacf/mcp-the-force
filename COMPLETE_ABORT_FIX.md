# Complete MCP Abort Fix - Both Issues Resolved

## The Two-Part Problem (Identified by Gemini 2.5 Pro)

### Issue 1: OpenAI Adapter Swallowing CancelledError
The OpenAI adapter was catching `CancelledError` and returning a normal response instead of re-raising it.

### Issue 2: ToolExecutor Converting Cancellation to Success
Even after fixing Issue 1, the ToolExecutor was catching `CancelledError` and returning an empty string, which FastMCP interpreted as a successful response.

## The Complete Fix

### 1. OpenAI Adapter (flow.py) - ALREADY FIXED
```python
# Changed from:
except asyncio.CancelledError:
    logger.info(f"Polling cancelled for {response_id}")
    return {"content": "", "response_id": "cancelled"}  # WRONG

# To:
except asyncio.CancelledError:
    logger.info(f"Polling cancelled for {response_id}")
    raise  # CORRECT
```

### 2. ToolExecutor (executor.py) - JUST FIXED
```python
# Changed from:
except asyncio.CancelledError:
    logger.info(f"[GRACEFUL] Tool execution cancelled...")
    return ""  # WRONG - sends success response

# To:
except asyncio.CancelledError:
    logger.info(f"[GRACEFUL] Tool execution cancelled...")
    raise  # CORRECT - lets FastMCP handle cancellation
```

## Why This Works

1. User aborts → Broken pipe → CancelledError
2. OpenAI adapter re-raises CancelledError ✓
3. OperationManager re-raises CancelledError ✓
4. ToolExecutor re-raises CancelledError ✓
5. FastMCP receives CancelledError and:
   - Does NOT send any response
   - Properly cancels all task groups
   - Cleans up orphaned tasks
6. No lingering tasks → No delayed crash → No AssertionError

## The Key Insight

The system was trying to be "helpful" by converting cancellations to empty success responses. But this prevented FastMCP from doing its proper cleanup, leaving orphaned OpenAI polling tasks that would crash the server when they eventually completed.

By letting CancelledError propagate all the way up, FastMCP can handle the abort properly and ensure no orphaned tasks remain.
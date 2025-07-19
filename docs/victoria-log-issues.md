# Post-Mortem: The VictoriaLogs Blocking Event Loop Incident

## Abstract

This post-mortem documents a critical production issue where the MCP Second-Brain server would consistently hang on the second query within a session. After an extensive debugging effort that took longer than implementing the entire project, involving 23+ failed hypotheses and fixes, the root cause was identified as VictoriaLogs performing synchronous HTTP requests in the async event loop. Disabling VictoriaLogs completely resolved all symptoms.

## Timeline

- **Initial Report**: Server hangs on second query with same session ID
- **Investigation Duration**: Multiple days, longer than the entire project implementation
- **Resolution**: Disabled VictoriaLogs HTTP handler

## Symptoms

The issue presented with the following consistent symptoms:

1. **First query**: Always successful
2. **Second query**: Always hangs (regardless of time gap)
3. **Hang locations**: Varied randomly across different code paths:
   - Import statements (`from .vector_store import _is_supported_for_vector_store`)
   - Vector store creation
   - File duplicate checking
   - Batch file uploads
   - OpenAI API polling
   - Response handling after successful completion
   - Tool instance creation
4. **Cancel/abort**: Non-functional when hung (no [CANCEL] messages)
5. **Server state**: Completely unresponsive, requires restart
6. **False pattern**: Appeared to have 5-minute recovery window (coincidental)

## Failed Theories and Attempted Fixes

The following theories were investigated and fixes attempted, ALL of which failed to resolve the issue:

### 1. OpenAI SDK Issues
- **Theory**: Internal semaphore deadlock when cancelling operations
- **Fix**: Changed vector store deletion to background task
- **Result**: ❌ Still hangs

### 2. Client Singleton Corruption
- **Theory**: Global OpenAI client singleton with corrupted state
- **Fix**: Implemented OpenAIClientFactory with per-event-loop instances
- **Result**: ❌ Still hangs

### 3. Connection Pool Exhaustion
- **Theory**: HTTP connection pool exhaustion with 3-5 minute cleanup
- **Fixes**: 
  - Set `keepalive_expiry=60.0`
  - Changed timeouts from `None` to explicit values
  - Fixed SearchAttachmentAdapter creating duplicate connection pools
- **Result**: ❌ Still hangs

### 4. Thread Pool Exhaustion
- **Theory**: Default 10 workers insufficient for 80-100 file operations
- **Fix**: Increased workers to 50
- **Result**: ❌ Made it worse - now hangs on first query

### 5. Synchronous File I/O
- **Theory**: Blocking file operations in async context
- **Fix**: Wrapped all file I/O in `run_in_thread_pool()`
- **Result**: ❌ Hang moved to different location

### 6. Dynamic Imports in Async Functions
- **Theory**: Python import lock conflicts with async event loop
- **Fix**: Moved all imports to module level
- **Result**: ❌ Still hangs

### 7. Vector Store Limit (100 stores)
- **Theory**: Hitting OpenAI's 100 vector store limit
- **Investigation**: Found only 8/100 stores in use
- **Fix**: Built elaborate "Loiter Killer" service for lifecycle management
- **Result**: ❌ Still hangs (but Loiter Killer worked correctly)

### 8. Event Loop Conflicts
- **Theory**: Multiple event loops or custom selector issues
- **Fixes**:
  - Removed custom event loop creation
  - Disabled PollSelector policy
  - Let FastMCP manage its own event loop
- **Result**: ❌ Still hangs

### 9. State Contamination
- **Theory**: First query leaves corrupted state
- **Fix**: Aggressive state reset between queries:
  - Cancel all pending tasks
  - Clear singleton instances
  - Force close SQLite connections
  - Shutdown/recreate thread pool
  - Clear module caches
  - Force garbage collection
- **Result**: ❌ Caused server crashes

### 10. Async/Sync Mixing
- **Theory**: Incorrect mixing of sync/async code
- **Fixes**:
  - Fixed `await get_client()` (sync client) calls
  - Fixed memory storage using sync client with await
  - Moved blocking operations to thread pool
- **Result**: ❌ Still hangs

### 11. SQLite Deadlocks
- **Theory**: Session cache database locks
- **Fix**: Bypassed SQLite entirely with in-memory cache
- **Result**: ❌ Still hangs

### 12. Logging Infrastructure
- **Theory**: Synchronous logging operations
- **Fixes**:
  - Implemented QueueHandler for async logging
  - Added TimeoutLokiHandler
  - Reduced logging verbosity
- **Result**: ❌ Still hangs

### 13. OpenAI API Performance
- **Discovery**: Batch uploads taking 6-7x longer than normal (123s vs 15s)
- **Fix**: Implemented parallel batch uploads (10 concurrent)
- **Result**: ✅ Improved performance but ❌ didn't fix hangs

## The Investigation Process

The debugging effort revealed several patterns:

1. **Moving Target**: Each "fix" moved the hang to a different location
2. **Timing Dependent**: Hang location varied based on execution speed
3. **Stochastic Behavior**: Same code, different outcomes
4. **Resource Pattern**: Always occurred during file/logging operations

## Root Cause

After exhaustive investigation, the root cause was devastatingly simple:

**VictoriaLogs was performing synchronous HTTP requests in the async event loop.**

When logging operations occurred in tight loops (e.g., logging each of 90 duplicate files), the synchronous HTTP calls to VictoriaLogs would block the entire event loop, causing:
- Complete unresponsiveness
- Inability to process cancellation signals
- Appearance of hangs at random async operations

## Resolution

```python
# Added to server.py
if os.environ.get("DISABLE_VICTORIA_LOGS") == "1":
    # Only use stderr logging
    pass
else:
    # VictoriaLogs handler setup
```

**Result**: With `DISABLE_VICTORIA_LOGS=1`, the server handles multiple sequential queries perfectly with zero hangs or crashes.

## Lessons Learned

1. **Blocking I/O in async contexts is catastrophic** - Even logging can kill your async application
2. **Complex symptoms often have simple causes** - We investigated 23+ complex theories when the issue was basic blocking I/O
3. **Network-based logging requires async handling** - Always use QueueHandler or async-aware handlers
4. **Debug with `PYTHONASYNCIODEBUG=1`** - Would have caught slow callbacks immediately
5. **The most elaborate fixes often miss the real problem** - We built an entire microservice (Loiter Killer) to work around what was actually a logging issue

## Recommendations

1. **Immediate**: Keep VictoriaLogs disabled in production
2. **Short-term**: Implement proper async logging handler
3. **Long-term**: Add event loop health monitoring to catch blocking operations

## Conclusion

This incident demonstrates how a simple blocking I/O operation (synchronous HTTP logging) can manifest as complex, seemingly unrelated symptoms across an entire async application. The magnitude of the debugging effort - exceeding the time to build the entire project - underscores the importance of maintaining async hygiene throughout all layers of the application, including seemingly innocent operations like logging.
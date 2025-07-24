# Solved: The Second Query Hanging Issue

## 🎉 SOLVED: The Real Root Cause (2025-01-19)

After days of investigation involving 23+ failed theories, the root cause was shockingly simple:

**A synchronous `StreamHandler(sys.stderr)` was blocking the asyncio event loop when the stderr pipe buffer filled up.**

### The Actual Problem
```python
# The problematic configuration:
app_logger.addHandler(queue_handler)      # Non-blocking (VictoriaLogs) ✓
app_logger.addHandler(stderr_handler)     # BLOCKING (stderr) ✗
```

When processing 90+ files, each generating an INFO log message, the stderr pipe buffer would fill faster than the parent process could consume. The next `write()` would block the event loop thread in a kernel syscall, freezing the entire server.

### Why We Were Misled
When setting `DISABLE_VICTORIA_LOGS=1`, the code also changed stderr level to WARNING:
```python
stderr_handler.setLevel(logging.WARNING)  # This filtered out INFO logs!
```
We thought VictoriaLogs was the problem, but it was actually the reduction in log volume that "fixed" it.

### The Fix
Simply remove the stderr handler:
```python
# app_logger.addHandler(stderr_handler)  # Commented out
```

VictoriaLogs continues working perfectly through its QueueHandler. No hangs ever occur.

---

## Original Investigation Log

This document chronicles the extensive debugging journey for the MCP The-Force server hanging issue.

## Summary of Major Discoveries (2025-07-18)

Through extensive debugging of MCP server hangs, we discovered:

1. **VictoriaLogs Red Herring**: Initially thought synchronous HTTP logging was blocking
   - Implemented QueueHandler - didn't fix the issue
   - Real problem was stderr handler, not VictoriaLogs
   
2. **OpenAI API Performance Degradation**: Batch uploads taking 6-7x longer than normal
   - Not MCP-specific - affects raw OpenAI SDK
   - Variable performance: same upload can take 15s or 123s
   - Fixed with parallel batch uploads (10 concurrent batches)

3. **File Path Deduplication**: Implemented proper tracking in Loiter Killer
   - OpenAI doesn't deduplicate files, leading to duplicate uploads
   - Now tracks file paths as primary identifier

4. **Resource Exhaustion Pattern**: 3-5 minute recovery window
   - Initially misdiagnosed as connection pool exhaustion
   - Actually OpenAI API throttling/rate limiting

5. **Cross-Instance Impact**: Multiple Claude instances affected simultaneously
   - Shared services (VictoriaLogs, Loiter Killer) were initial suspects
   - Root cause was OpenAI account-level throttling

## 1. Intermittent Vector Store Creation Hang

**Status**: ✅ FIXED - Was caused by stderr pipe buffer blocking

**Symptoms**:
- First vector store creation works perfectly (completes in ~17 seconds)
- Second attempt hangs indefinitely at various locations
- No error messages or exceptions
- Server becomes unresponsive after hang

**Failed Test Sequence**:
1. Run Grok3 with full codebase context → ✅ Success (vector store created in 17s)
2. Run o3 with full codebase context → ✅ Success 
3. Run o3 again with same context → ❌ Hangs at random location

**Debugging Observations**:
- Hang locations varied: imports, file operations, API calls, vector store creation
- Never consistent - depended on when pipe buffer filled
- Cancel/abort didn't work - event loop blocked in syscall
- VictoriaLogs QueueHandler was working correctly

**Root Cause FOUND (2025-01-19)**: Blocking stderr handler
- 90+ INFO log messages during file operations
- Filled stderr pipe buffer faster than parent could consume
- `write()` syscall blocked the event loop thread
- Removing stderr handler completely fixed the issue

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
- **Fix**: Aggressive state reset between queries
- **Result**: ❌ Caused server crashes

### 10. Async/Sync Mixing
- **Theory**: Incorrect mixing of sync/async code
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
- **Result**: ❌ Still hangs (but was on the right track!)

### 13. OpenAI API Performance
- **Discovery**: Batch uploads taking 6-7x longer than normal (123s vs 15s)
- **Fix**: Implemented parallel batch uploads (10 concurrent)
- **Result**: ✅ Improved performance but ❌ didn't fix hangs

## Lessons Learned

1. **Never do blocking I/O in the event loop** - Not even logging to stderr!
2. **Test theories in isolation** - We disabled VictoriaLogs AND changed log level together
3. **Simple bugs have complex symptoms** - A basic stderr write caused 23+ failed theories
4. **Pipes are bounded buffers** - They can and will block your application
5. **AsyncIO debugging is hard** - Hangs appear at random locations, not the actual cause

## Testing Notes

### Standard Test Query for Reproduction:
```python
# First query (usually succeeds)
mcp__second-brain__chat_with_o3(
    instructions="List 3 weird things about this codebase in one paragraph",
    output_format="One paragraph listing 3 weird/unusual things",
    context=["/Users/luka/src/cc/mcp-the-force"],
    session_id="test-hang-issue-001",
    reasoning_effort="low"
)

# Second query (would hang before fix)
mcp__second-brain__chat_with_o3(
    instructions="What are the 3 most complex parts of this codebase?",
    output_format="One paragraph describing the 3 most complex parts",
    context=["/Users/luka/src/cc/mcp-the-force"],
    session_id="test-hang-issue-001",
    reasoning_effort="low"
)
```

**Expected behavior (after fix)**:
- First query: Completes successfully
- Second query: Completes successfully
- No hangs, no server restarts needed

---

The remaining content below documents the investigation process and is preserved for historical reference...
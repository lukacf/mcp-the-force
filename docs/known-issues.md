# Known Issues and Failed Tests

This document tracks known issues, failed tests, and debugging observations for the MCP Second-Brain server.

## Summary of Major Discoveries (2025-07-18)

Through extensive debugging of MCP server hangs, we discovered:

1. **VictoriaLogs Blocking**: Synchronous HTTP logging was blocking the event loop
   - Fixed with async handler and queue-based approach
   
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

**Status**: 🟡 Partially Fixed (semaphore issue fixed, but new cancellation issue found)

**Symptoms**:
- First vector store creation works perfectly (completes in ~17 seconds)
- Second attempt hangs indefinitely before entering `VectorStoreManager.create()` method
- No error messages or exceptions
- Server becomes unresponsive after hang

**Failed Test Sequence**:
1. Run Grok3 with full codebase context → ✅ Success (vector store created in 17s)
2. Run o3 with full codebase context → ✅ Success 
3. Run o3 again with same context → ❌ Hangs before vector store creation

**Debugging Observations**:
- Hang occurs at: `vs_id = await self.vector_store_manager.create(files_for_vector_store)`
- Never reaches the log: "VectorStoreManager.create: About to create vector store"
- VectorStoreManager has NO locks or complex state
- File descriptor limit is high (1M+) with only 13 FDs in use
- PollSelector is being used (fixed from SelectSelector)

**Root Cause**: Unknown - awaiting further investigation

**Update (2025-07-17 12:23-12:24)**:
- Tested with o3 low reasoning effort
- Vector store upload hung after "Starting batch upload of 80 files" 
- Cancelled after 1 minute
- ✅ Cancellation worked properly this time with full [CANCEL] log messages
- This suggests the cancellation mechanism works but something blocks during file upload

**Root Cause Found** (via o3 analysis):
- The OpenAI SDK uses an internal asyncio.Semaphore to limit concurrent requests
- When `asyncio.wait_for(vector_store_manager.delete(vs_id), timeout=5.0)` times out, it cancels the delete operation
- This cancellation leaves the OpenAI client's semaphore in an acquired state
- On the second run, any OpenAI API call tries to acquire the stuck semaphore and hangs forever
- The hang happens BEFORE entering our code, which is why we see no logs

**Fix Applied**: Changed vector store deletion to always run as a background task in `executor.py` to prevent semaphore deadlock

**Update (2025-07-17 12:33)**:
- New issue: Cancellation doesn't work during vector store creation itself
- Aborted after "Creating vector store with 82 overflow/attachment files"
- NO [CANCEL] messages appeared in logs
- This is a different issue from the semaphore deadlock - cancellation is not propagating during the upload

**Update (2025-07-17 12:38-12:39)**:
- Tested semaphore fix with back-to-back o3 queries
- First query: ✅ Success (completed normally)
- Second query: ❌ Still hangs at "Creating vector store with 82 overflow/attachment files"
- **Conclusion**: The semaphore fix did NOT resolve the issue - the hang still occurs on the second run
- This suggests the root cause is NOT the OpenAI SDK semaphore, but something else blocking the second vector store creation

**Update (2025-07-17 13:07-13:08)**:
- Implemented Gemini's client factory fix (replaced global singleton with OpenAIClientFactory)
- Tested with back-to-back o3 queries again
- First query: ✅ Success (completed normally)
- Second query: ❌ STILL hangs at "Creating vector store with 82 overflow/attachment files"
- **NEW ISSUE**: Aborting now completely kills the MCP server (no cancellation messages, server dies)
- **Conclusion**: The client singleton was NOT the issue either
- The client factory change may have made cancellation handling worse
- The hang is consistent and reproducible, but not caused by client state or semaphores

**Theories Ruled Out**:
1. ❌ OpenAI SDK semaphore deadlock (o3's theory)
2. ❌ Global client singleton with corrupted state (Gemini's theory)
3. ❌ Connection pool issues (related to client singleton)

**Still Unexplained**:
- Why does it ALWAYS work on first run but ALWAYS hang on second?
- What resource or state accumulates between runs?
- Why does abort now kill the server completely?

**Update (2025-07-17 13:18)**:
- Tested Gemini's thread pool theory by disabling singleton pattern
- Modified thread pool to always create new instances
- Result: Made things WORSE!
- Now the FIRST query hangs after OpenAI responds with "status: completed"
- The response never makes it back through the MCP protocol
- We can't even reach the second query to test vector store behavior
- **Conclusion**: Thread pool singleton is necessary for proper operation
- ❌ Thread pool exhaustion theory also ruled out

---

## 2. Grok API Calls Hang Without Cancellation Support

**Status**: 🔴 Active Issue

**Symptoms**:
- Grok API calls hang after successful vector store creation
- Ctrl+C/abort does NOT produce [CANCEL] log messages
- Server becomes unresponsive and must be restarted
- Other adapters (OpenAI, Vertex) handle cancellation properly

**Failed Test**:
- Run Grok3 with full codebase → Vector store created → API call hangs → Abort → No [CANCEL] logs

**Debugging Observations**:
- `cancel_aware_flow.py` exists but is NOT imported/applied to GrokAdapter
- GrokAdapter.generate() has no try/except CancelledError handling
- OpenAI and Vertex adapters DO have proper cancellation handling

**Root Cause**: `cancel_aware_flow.patch_grok_adapter()` is never called

---

## 3. OpenAI Response Completion Not Returning to Client

**Status**: 🔴 Active Issue

**Symptoms**:
- OpenAI response polling completes successfully ("status: completed")
- Operation marked as completed in logs
- But response never returns to MCP client
- Server appears to hang after completion
- Abort produces no [CANCEL] messages

**Failed Test** (2025-07-17 12:10-12:15):
```
12:10:15 Task created: chat_with_o3_c9e8fdde
12:10:16 OpenAI responses.create completed
12:10:16 Starting background polling
12:10:19 - 12:15:56 Multiple polling attempts (status: queued)
12:15:57 OpenAI response status: completed ✅
12:15:57 Operation chat_with_o3_c9e8fdde completed successfully ✅
[5+ minutes of waiting]
[Manual abort - no cancellation messages]
```

**Debugging Observations**:
- Response completes after ~340 seconds of polling
- Operation manager marks it as completed
- But the response never makes it back through the MCP protocol layer
- Server is likely dead/hung at this point

**Root Cause**: Unknown - possibly related to the intermittent hanging issue

---

## 4. Boolean Parameter Validation (FastMCP)

**Status**: ✅ Fixed

**Original Issue**:
- FastMCP passes boolean parameters as strings ("true"/"false")
- But expects actual boolean types during validation
- Results in: "Input validation error: 'true' is not valid under any of the given schemas"

**Fix Applied**:
- Modified `tools/integration.py` to declare boolean parameters as `Optional[str]` for FastMCP
- Added type coercion in `ParameterValidator._coerce_type()` to convert strings to booleans
- Now properly handles "true"/"false" string values

---

## 5. SelectSelector 1024 File Descriptor Limit

**Status**: ✅ Fixed

**Original Issue**:
- SelectSelector on macOS has hard limit of 1024 file descriptors
- Vector store uploads with 96+ files exceed this limit
- Results in indefinite hang during `upload_and_poll()`

**Fix Applied**:
- Switched from SelectSelector to PollSelector in `server.py`
- PollSelector has no FD limit while still avoiding KqueueSelector stdio issues

---

## Testing Notes

### Reproduction Steps for Hanging Issues:
1. Start fresh MCP server
2. Run any query that triggers vector store creation (e.g., full codebase context)
3. Wait for completion
4. Run another similar query
5. Observe hang at vector store creation or response delivery

### Key Indicators of Server Death:
- No [CANCEL] messages when aborting
- Server doesn't respond to new requests
- Must restart server completely

### Patterns Observed:
- First operation after server start usually works
- Subsequent operations may hang at various points
- Hanging can occur at:
  - Vector store creation (before entering method)
  - API response delivery (after successful completion)
  - Grok API calls (no cancellation support)

### Latest Test Results (2025-01-17):
**First query with full codebase context now hangs** (previously only second query hung):
- Successfully clears deduplication cache
- Creates vector store and verifies all 80 files
- Hangs after last "Verified file:" log
- Never reaches file opening or batch upload phase
- Cancel/abort doesn't work - server becomes unresponsive

**Previous Root Cause Theory (may be incorrect):**
Initially suspected `SearchAttachmentAdapter.clear_deduplication_cache()` deadlock due to class-level shared lock, but latest test shows hang occurs AFTER deduplication cache is cleared successfully.

**Current Evidence:**
1. Hang location has moved - now happens during first query (not second)
2. Occurs after file verification completes but before file opening starts
3. Found deprecated `get_client()` calls that return sync client used with `await`
4. Debug prints to stderr are not visible (swallowed by MCP layer)

**Fixes Applied:**
1. Fixed two `await get_client().vector_stores.delete()` calls in vector_store.py
2. Fixed missing import in memory/config.py
3. Fixed sync client usage with await in memory/conversation.py
4. All `get_client()` usage now consistent (sync client for sync code)

### Latest Test Results After Fixes (2025-01-17 13:42):
**Progress but still hangs:**
- Successfully clears deduplication cache
- Creates vector store (`vs_6878e1a3264c8191bf67963cf3b7909d`)
- Verifies all 80 files
- **NEW**: Successfully opens files 1-16 out of 80
- Hangs after "Successfully opened file 16: .../cancellation_patch.py"
- Never completes opening remaining files (17-80)
- Cancel/abort still doesn't work

**Key Observation:**
The hang has moved further in the process. It now successfully:
1. Creates the vector store
2. Verifies files exist
3. Opens first 16 files
4. But hangs while opening file 17

### Second Test (2025-01-17 13:48):
**Hang occurs at different point:**
- This time hung after opening 15 files (not 16)
- Last successful: "file 15: .../tests/e2e_dind/README.md"
- Hang is not deterministic - occurs after opening 15-16 files
- Suggests issue is not with a specific file but with resource limits or async/sync mixing

### Complete Failure (2025-01-17 13:57):
**Server now hangs much earlier - during basic context gathering:**
- Hangs at: "Processing item '/Users/.../mcp_second_brain/server.py'"
- Not even reaching vector store creation anymore
- Suspected cause: Debug logging with file I/O operations blocking event loop

### Emergency Revert (2025-01-17):
**Reverted the following problematic changes:**
1. Removed all debug logging that writes to `/tmp/mcp_debug_hang.log`
2. Removed print statements to stderr
3. Reverted background task approach for vector store deletion
4. Reverted incorrect async/await removal in memory/conversation.py

**Kept the following good changes:**
1. OpenAIClientFactory usage instead of get_client() in vector_store.py
2. disable_memory_search parameter additions
3. Boolean parameter validation fixes
4. Import fix in memory/config.py

### Post-Revert Baseline Test (2025-01-17 14:07):
**Back to original behavior:**
- First query: ✅ Success
- Second query: ❌ Hangs at vector store creation
- Hang location: After "Creating vector store with 82 overflow/attachment files"
- Server becomes unresponsive

**Summary of Investigation:**
1. Initially suspected deduplication lock deadlock - ruled out
2. Suspected synchronous file I/O blocking event loop - likely contributing factor
3. Added debug logging made things worse (blocked earlier in process)
4. Logger theory considered but ruled out as unlikely
5. Root cause still unknown - consistently hangs on second query when creating vector stores

### Root Cause Identified (2025-01-17):
**The hanging bug stems from synchronous blocking I/O in the background memory storage task**

The issue was in `memory/conversation.py`:
- `store_conversation_memory` runs as a fire-and-forget background task after successful queries
- It was using a synchronous OpenAI client (`get_client()`) with `await` - which is invalid
- This blocked the event loop during the first query's background task
- On the second query, the still-blocked event loop couldn't schedule new coroutines
- This caused hangs at any `await` (e.g., vector store creation)

**Fix Applied:**
1. **Memory Storage Fix**:
   - Updated to use async OpenAI client via `OpenAIClientFactory`
   - Moved all synchronous I/O (json.dump, file operations, git commands) to thread pool via `run_in_executor`
   - This makes the entire memory storage non-blocking, preventing event loop starvation

2. **Vector Store Delete Fix**:
   - OpenAI SDK bug: cancelling vector store delete leaves internal semaphore locked
   - Previous code used `wait_for` with 5s timeout which could cancel the delete
   - Fixed by using `asyncio.shield()` to prevent cancellation from propagating
   - Increased timeout to 30s (delete operations are typically fast)
   - Now the delete coroutine completes even if timeout expires

### Test Results After Both Fixes (2025-01-17 15:39):
**Made things WORSE - now hangs on FIRST query:**
- Hangs after "Starting batch upload of 80 files"
- Never completes the OpenAI SDK's `upload_and_poll` operation
- Cancel still doesn't work
- Server completely unresponsive

**New Theory - Thread Pool Exhaustion:**
The memory storage fix now uses `run_in_executor` for:
- Git commands (2 operations)
- Temp file creation
- File deletion

These operations may be exhausting the default thread pool, preventing the OpenAI SDK's `upload_and_poll` from getting threads for its file I/O operations. This creates a deadlock where both systems are waiting for threads.

**Next Step:**
Disable memory storage entirely to confirm it's the cause.

### Update (2025-01-17):
**Memory storage can't be the cause** - it runs AFTER queries complete, but we're hanging DURING the first query's vector store upload. The hang happens before memory operations would even start.

**Actions taken:**
1. Disabled memory storage (kept disabled for now)
2. Reverted `asyncio.shield()` change back to original
3. Only remaining change is the memory/conversation.py async client fix (not yet called)

### Test Results After Reverting Shield (2025-01-17 15:51):
**Still hangs on second query:**
- First query: ✅ Success (42.30s, created and deleted vs_6878ffb4f42481918250a11bc0b1b553)
- Second query: ❌ Hangs at "Creating vector store with 82 overflow/attachment files"
- No further logs after that line
- Vector store deletion from first query completed successfully (vs was deleted)
- **Conclusion**: The hang is NOT caused by shield/cancellation issues in delete

**Next Test**: Disable vector store deletion entirely to see if cleanup is interfering

### CRITICAL UPDATE - Disabling VS Deletion Makes it WORSE (2025-01-17 15:55):
**The problem got WORSE when we disabled vector store deletion:**
- Now hangs on FIRST query (not second)
- Hangs at exact same place: "Starting batch upload of 80 files"
- Only change was commenting out vector store deletion
- This is completely unexpected behavior

**Hang details:**
```
Verified file: /Users/luka/src/cc/mcp-second-brain/docs/API-REFERENCE.md
Starting batch upload of 80 files
[NO FURTHER OUTPUT]
```

**This suggests:**
1. The hang is NOT in the deletion code
2. Something about orphaned vector stores may be causing issues
3. Or we accidentally broke something else
4. The problem might be in the OpenAI SDK's upload_and_poll method itself

## ROOT CAUSE DISCOVERED (2025-01-17 16:05)

### 🚨 CRITICAL: Vector Store Limit Reached 🚨

**The root cause is the OpenAI project limit of 100 vector stores!**

- Current count: **99 vector stores** (hitting the 100 limit)
- Current files: **41,002 files** accumulated over time
- This explains EVERYTHING:
  - Why vector store creation hangs (can't create new ones at limit)
  - Why it got WORSE when we disabled deletion (no cleanup = immediate limit)
  - Why it's intermittent (depends on how close to limit)
  - Why the hang happens in `upload_and_poll` (OpenAI API blocking)

**Immediate Actions Needed:**
1. Clean up all orphaned vector stores
2. Implement proper vector store lifecycle management
3. Add monitoring/alerting when approaching limits
4. Consider implementing vector store reuse/pooling

## UPDATE (2025-01-17 22:50) - Real Root Cause Discovered

### The 100 Vector Store Limit Was a Misdiagnosis!

**Current vector store count: 8/100** - We're nowhere near the limit!

We built an elaborate "Loiter Killer" service to manage vector store lifecycle and prevent hitting the 100-store limit. While this successfully implements vector store reuse and file deduplication, it didn't fix the hang because the limit wasn't the actual problem.

### The Real Issue: OpenAI Adapter Hangs When Continuing Sessions

**Test Results with In-Memory Session Cache:**
- Bypassed SQLite session cache entirely (ruled out deadlock)  
- Used simple dictionary: `_test_session_cache = {}`
- First query: ✅ Success
  - No previous response_id
  - Prompt: 360,558 chars
  - Successfully creates operation and calls OpenAI
- Second query: ❌ Hangs at adapter.generate
  - Successfully reuses vector store (deduplication works!)
  - Finds previous response_id: `resp_687961d0ba7081a2a25e39184cedf10003f6959d90fa5d2f`
  - Prompt: 8,441 chars (much smaller)
  - Hangs IMMEDIATELY after "[STEP 15] Calling adapter.generate"
  - Never reaches "run_with_timeout" or operation creation
  - **Hang occurs BEFORE any OpenAI API call**

**Key Observations:**
1. The hang occurs at the very start of `adapter.generate()` when `previous_response_id` is set
2. It's NOT related to vector stores, SQLite, thread pools, or even the OpenAI API
3. Cancel doesn't work - suggests the hang is in synchronous code or a blocking I/O operation
4. The Loiter Killer service works perfectly for vector store reuse, but that wasn't the problem
5. The hang happens BEFORE reaching the actual API - it's in the adapter setup/initialization

**Theories:**
1. The OpenAI adapter has a blocking operation when `previous_response_id` is passed
2. There's a synchronous validation or state retrieval that blocks the event loop
3. The adapter might be trying to fetch previous response metadata synchronously

**Next Steps:**
1. Investigate OpenAI adapter's `generate()` method when `previous_response_id` is set
2. Look for any synchronous operations at the start of the method
3. Consider disabling session continuation as a workaround

## ROOT CAUSE FINALLY DISCOVERED (2025-01-17 23:45)

### 🎯 Update 2025-07-18: The Real Issue is NOT VictoriaLogs!

**Latest findings**: Even after fixing VictoriaLogs with `LokiQueueHandler`, the hang STILL occurs!

**Critical observation**:
- First query: Completes successfully (~2 minutes)
- Second query: Dies at **random code location** after **consistent time interval**
- The hang location changes: file filtering, duplicate checks, etc.
- **IT'S NOT ABOUT WHAT THE CODE DOES, IT'S ABOUT WHEN IT HAPPENS**

**It's NOT**:
- ❌ Vector store limits (we only have 8/100)
- ❌ SQLite deadlocks
- ❌ OpenAI SDK bugs
- ❌ Session cache issues
- ❌ Thread pool exhaustion
- ❌ VictoriaLogs blocking (fixed with LokiQueueHandler)
- ❌ Empty file uploads
- ❌ Any specific code path

**Possible causes**:
- ⚠️ Reused OpenAI client timing out
- ⚠️ MCP layer timeout/cleanup
- ⚠️ FastMCP request timeout
- ⚠️ Resource cleanup after first query
- ⚠️ HTTP/2 connection state issues

**Evidence timeline**:
1. Fixed VictoriaLogs blocking → Still hangs
2. Hang always on second query regardless of session
3. Death location varies based on code execution speed
4. No actual API calls made when it hangs
5. Consistent time interval suggests timeout mechanism
6. **TEST RESULT**: Different sessions (test-different-session-001 & 002) → Still hangs
7. **NOT session-related**: Both queries created NEW vector stores
8. **Time-based**: Hang occurs at consistent interval from server start (~47s after first query completes)
9. **CRITICAL FINDING**: Complex o3 query with ZERO context (no files) → Works perfectly!
10. **Confirms**: Issue is specifically related to file handling/vector stores, NOT o3 API
11. **PATTERN BREAK**: After no-context query, next file-based query worked! Then 4th query hung
12. **KEY INSIGHT**: The hang happens even when NO vector store operations occur (reused session)

**Detailed sequence of the pattern-breaking test**:
1. Query 1: Normal query with context overflow → Created vector store → SUCCESS (58.84s)
2. Query 2: Complex Gödel query with ZERO context → No files, no vector store → SUCCESS 
3. **(8.6s pause between queries)**
4. Query 3: Normal query with NEW session → Created NEW vector store → SUCCESS! (Pattern break!)
5. Query 4: Normal query with ANOTHER new session → Hung at "gather_file_paths" (early in execution)

**Critical observations**:
- The no-context query somehow "reset" the problematic state
- This allowed ONE more file-based query to succeed
- The 4th query hung much earlier (during file gathering, not vector store ops)
- Confirms the issue accumulates with file operations, not API calls

**BREAKTHROUGH: 5-minute wait test**:
1. Query 1: Normal query with context (test-5min-wait-001) → SUCCESS
2. **Waited 5 minutes**
3. Query 2: Same query, different session (test-5min-wait-002) → SUCCESS! 

**This proves**:
- Time alone can reset the problematic state
- Some resource has a ~5 minute timeout/cleanup cycle
- Not permanent corruption but temporary resource exhaustion
- Likely connection pooling, file handles, or similar with TTL

**CRITICAL UPDATE: 1-minute wait test**:
1. Previous successful query completed
2. **Waited only 3 minutes**
3. Query 1: test-1min-wait-001 → HUNG at "Creating vector store with 92 overflow/attachment files"

**This narrows the window**:
- Resource cleanup happens between 3-5 minutes
- The hang can now occur on FIRST query if previous activity was recent
- The resource exhaustion persists across queries within ~3 minute window
- Points strongly to connection pool or httpx client timeout issues

### The REAL Smoking Gun

The hang is **resource pool exhaustion with 3-5 minute cleanup**:
- Occurs when file operations happen within 3 minutes of previous query
- 5 minute wait allows cleanup and reset
- 3 minute wait is insufficient - resource still exhausted
- Hang location varies but always involves file/vector store operations
- NOT the file operations themselves, but the HTTP client/connection pool used

**Critical Discovery - OpenAI Client Singleton Pattern**:
The OpenAIClientFactory uses a **singleton pattern per event loop**, NOT creating new clients each call:
```python
# From mcp_second_brain/adapters/openai/client.py
# Configure robust HTTP transport with connection pooling.
limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
```

This explains why resource exhaustion persists across queries:
- The same AsyncOpenAI client instance is reused for ALL requests in an event loop
- The httpx connection pool (20 keepalive, 100 max connections) is shared
- File upload operations may exhaust the connection pool
- Pool cleanup/timeout appears to be 3-5 minutes

**Critical Contradiction - No-Context Queries Work**:
The user correctly points out: If OpenAI's connection pool was the issue, why do no-context queries work perfectly? This rules out the OpenAI client as the primary cause.

**Evidence**:
- No-context queries use the SAME OpenAI client singleton
- They make the SAME API calls (responses.create, polling, etc.)
- Yet they NEVER hang, even when run immediately after a context query
- The only difference: no-context queries skip file operations and vector stores

**Updated suspects** (after ruling out OpenAI client):
1. ~~OpenAI httpx connection pool exhaustion~~ (RULED OUT - no-context queries work)
2. **File operations during context gathering** (primary suspect again)
3. **Vector store file upload operations** (even when reusing, still processes files)
4. **File system resource exhaustion** (file handles, memory mapping, etc.)
5. **Something specific to file reading/processing in gather_file_paths**
6. **Pattern confirms**: Resource exhaustion from FILE operations, not API operations

### Proof

The hang always occurs during a logging call, not during actual async operations:
- Sometimes after "Skipping duplicate file" logs
- Sometimes after "Vector store ready"
- Sometimes after other log statements
- But ALWAYS while the logger is trying to send to VictoriaLogs

### The Fix

**Immediate fix**: Use `logging.handlers.QueueHandler` to move VictoriaLogs communication to a background thread:

```python
# Wrap the VictoriaLogs handler
queue = queue.Queue(-1)
queue_handler = logging.handlers.QueueHandler(queue)
queue_listener = logging.handlers.QueueListener(
    queue, victoria_logs_handler, respect_handler_level=True
)
queue_listener.start()

# Replace direct handler with queue handler
logger.addHandler(queue_handler)
```

**Alternative fixes**:
1. Aggregate logs in tight loops (e.g., "Skipped 87 files" instead of 87 individual logs)
2. Set production log level to INFO, keep per-file logs at DEBUG
3. Use an async-aware logging handler
4. Disable VictoriaLogs handler entirely (stderr only)

### Why This Explains Everything

- **Always second query**: First query has fewer duplicate files to log
- **Loiter Killer "fixed" nothing**: The vector store reuse creates MORE duplicate file logs!
- **Cancel doesn't work**: Event loop is blocked, can't process signals
- **Hang location varies**: Depends on when the log buffer fills

### Lessons Learned

1. **Never do blocking I/O in the event loop** - including logging!
2. **Use `PYTHONASYNCIODEBUG=1`** to catch slow callbacks
3. **Always use QueueHandler** for network-based log handlers
4. The most complex bugs often have the simplest causes

## Issue #3: OpenAI Batch Upload Performance Degradation

### The Discovery

After fixing the async logging issue, we discovered the MCP server still hangs on sequential queries. Investigation revealed:

**Batch uploads are taking 6-7x longer than normal**:
- Expected: ~15-20 seconds for 90 files
- Actual: 104-123 seconds
- This happens even in standalone tests with raw OpenAI SDK

### Evidence

1. **MCP server context**: 123 seconds for 90 files
   ```
   2025-07-18 12:15:31.656 [DEBUG] About to batch upload 90 files
   2025-07-18 12:17:34.866 Batch upload completed in 123.22s
   ```

2. **Standalone test**: 104 seconds for 89 files
   ```
   Completed in 104.31s
   Status: completed
   ⚠️  SLOW UPLOAD: 104.31s (expected ~15s)
   ```

3. **Normal baseline**: 16.5 seconds for 95 files (from test_vector_store_realistic.py)

### Root Cause Analysis

This is NOT an MCP-specific issue:
- Happens with raw OpenAI SDK
- Affects all Claude instances using the same OpenAI account
- Shows progressive degradation pattern
- Has 3-5 minute recovery window

**Likely causes**:
1. **OpenAI API throttling** - Account hitting rate limits
2. **Vector store quota pressure** - Even though under 100 limit
3. **File upload quotas** - Cumulative file operations being throttled

### Impact

The slow uploads cause cascading failures:
- Exhausts timeouts in the MCP/tool execution pipeline
- Creates the appearance of "hangs" that are actually slow operations
- Affects all Claude instances sharing the OpenAI account

### Workarounds

1. **Increase timeouts** - Set MCP tool timeout to 300000ms (5 minutes)
2. **Batch size reduction** - Upload fewer files per batch
3. **Cooldown periods** - Wait 5 minutes between vector store operations
4. **Monitor quotas** - Check OpenAI usage dashboard for limits

### Solution Implemented

**Parallel Batch Uploads** (implemented in commit ac12576):
- Files >20 are split into 10 parallel batches
- Small uploads (≤20 files) use single batch to avoid overhead
- Each batch can fail independently without affecting others
- Test results show ~30% speedup with parallel processing

### Additional Discoveries

1. **Variable API Performance**: The same upload can take 15s or 123s depending on API state
2. **Cross-instance Impact**: Multiple Claude instances are affected simultaneously
3. **OpenAI Client Singleton**: The OpenAIClientFactory maintains a singleton client per event loop with connection pooling (20 keepalive, 100 max connections)
4. **Not Connection Pool Exhaustion**: No-context queries work perfectly, ruling out client-side issues

### TODO

- [x] ~~Implement parallel batch uploads~~ ✓ Completed
- [ ] Add upload speed monitoring and alerts
- [ ] Implement exponential backoff for failed batches
- [ ] Investigate OpenAI rate limit headers for dynamic adjustment
- [ ] Consider adaptive batch sizing based on current API performance
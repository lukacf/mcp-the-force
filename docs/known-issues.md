# Known Issues and Failed Tests

This document tracks known issues, failed tests, and debugging observations for the MCP Second-Brain server.

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
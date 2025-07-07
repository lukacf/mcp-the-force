# Context and Vector Database Management Redesign

## Table of Contents
1. [Background](#background)
2. [System Overview](#system-overview)
3. [Current Problems](#current-problems)
4. [Constraints](#constraints)
5. [Proposed Solution: Stable-Inline List](#proposed-solution-stable-inline-list)
6. [Implementation Details](#implementation-details)
7. [Trade-offs](#trade-offs)
8. [Migration Plan](#migration-plan)

## Background

MCP Second-Brain is a Model Context Protocol (MCP) server that provides Claude (and other AI assistants) with access to multiple AI models (OpenAI o3/o3-pro, Google Gemini, GPT-4.1) for collaborative problem-solving. 

### Critical Architecture Understanding

- **Claude**: The USER of the MCP Second-Brain system - calls tools to consult other models
- **O3, Gemini, etc**: The ASSISTANTS that receive context and answer questions
- **Session**: A conversation thread with a specific assistant, identified by `session_id`
- **Context**: Files that should be available throughout the conversation with an assistant
- **Attachments**: Files for one-time retrieval/search operations
- **Vector Store**: OpenAI's hosted vector database for semantic search over large file sets

## System Overview

### How It Works

1. **Claude initiates a conversation** with an assistant by calling a tool:
   ```python
   chat_with_o3(
       session_id="implement-auth-system",
       instructions="Review this authentication implementation",
       context=["/api/auth", "/api/middleware"],
       attachments=["/docs/security-guidelines.pdf"]
   )
   ```

2. **The system processes the request**:
   - Loads all files from `context` paths
   - Calculates total token count
   - If within assistant's limit: includes files directly in prompt
   - If exceeds limit: puts overflow files in a vector store
   - Creates a temporary vector store for attachments + overflow
   - Sends request to the chosen assistant model

3. **Session continuity**:
   - The `session_id` maintains conversation thread continuity
   - Multiple calls with the same `session_id` continue the conversation
   - Sessions persist across different Claude conversations with humans
   - When assistant's context window fills up, that session ends (no compaction)

### Current Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│                 │     │                  │     │                 │
│  Claude (User)  │────▶│  MCP Second-     │────▶│  AI Assistants  │
│                 │     │  Brain Server    │     │  (o3, Gemini)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │  Vector Store    │
                        │  (OpenAI)        │
                        └──────────────────┘
```

## Current Problems

### Problem 1: Context Overflow Unpredictability

**The Issue**: When context files exceed an assistant's token limit, the system must split them between inline (in the prompt) and vector store (external). This split is unpredictable and changes between calls.

**Example Scenario**:
```
Turn 1: context=["/api"] (100 files, 300k tokens for o3 with 200k limit)
- Files A-M (150k tokens) → inline
- Files N-Z (150k tokens) → vector store

Turn 2: context=["/api", "/tests"] (120 files, 350k tokens)
- Files A-K (140k tokens) → inline  (M is now in vector store!)
- Files L-Z + tests (210k tokens) → vector store
```

File M moved from inline to vector store between turns, even though it didn't change. This unpredictability makes it hard to reason about what the assistant has direct access to.

**Current Behavior**:
- Vector stores are created fresh for each call
- Deleted immediately after the call completes
- No persistence between calls

### Problem 2: Context Duplication in Assistant History

**The Issue**: Each call resends all context files, even unchanged ones. This wastes tokens in the assistant's limited context window.

**Example**:
```
Turn 1: Send /api/server.go (1000 tokens) → Assistant has 1000 tokens used
Turn 2: Send /api/server.go again → Assistant has 2000 tokens used (duplicated!)
Turn 3: Send /api/server.go again → Assistant has 3000 tokens used (tripled!)
```

By turn 10, the same file might appear 10 times, rapidly exhausting the assistant's context window.

## Constraints

### Hard Requirements

1. **Security**: Absolute isolation between different human users' conversations
2. **No persistent vector stores**: We cannot predict when sessions end
   - Sessions might be abandoned after one use
   - Or resumed months later
   - No cleanup events to hook into
3. **No background workers**: MCP design principles forbid stateful background processes
4. **Minimal state storage**: Cannot store unbounded per-file tracking data
5. **Cost control**: OpenAI charges for vector store storage after 1GB

### Technical Constraints

1. **OpenAI Vector Store Limitations**:
   - Supports add/remove operations but not in-place updates
   - 10k file limit per store
   - API operations can be slow
   
2. **Assistant Context Windows** (fixed, no compaction):
   - o3/o3-pro: ~200k tokens
   - Gemini 2.5: ~1M tokens
   - GPT-4.1: ~1M tokens
   - When full, session ends - no gradual eviction

3. **Session Model**:
   - Sessions are just strings, not objects with lifecycles
   - No way to know when a session is "done"

## Proposed Solution: Stable-Inline List

### Core Concept

Instead of complex hashing or diff systems, maintain a simple "stable-inline list" that records which files were sent inline during the first overflow event. This list remains fixed for the session lifetime, ensuring predictable behavior.

### How It Works

#### First Call with Overflow

```python
# User calls with large context
context = ["/api", "/lib"]  # 200 files, 500k tokens

# 1. Sort files deterministically (by size, then name)
sorted_files = sort_by_size_then_name(context)

# 2. Fill inline budget
inline_files = []
overflow_files = []
budget = calculate_token_budget()  # e.g., 150k tokens

for file in sorted_files:
    tokens = count_tokens(file)
    if tokens <= budget:
        inline_files.append(file)
        budget -= tokens
    else:
        overflow_files.append(file)

# 3. Save the stable list (first time only)
save_stable_list(session_id, inline_files)  # ~50KB for 1000 paths

# 4. Create ephemeral vector store
vector_store_id = create_vector_store(overflow_files + attachments)

# 5. Send to assistant
prompt = format_prompt(inline_files, vector_store_info)
```

#### Subsequent Calls

```python
# User calls again
context = ["/api", "/lib"]  # Some files may have changed

# 1. Load the stable list
stable_list = get_stable_list(session_id)

# 2. Process files according to stable list
inline_files = []
overflow_files = []

for file in context:
    if file in stable_list:
        # This file was inline before
        if file_changed_since_last_send(file):  # mtime/size check
            inline_files.append(file)  # Resend changed version
        # else: skip - assistant already has it
    else:
        # This file always goes to vector store
        overflow_files.append(file)

# 3. Handle new files not in original context
new_files = set(context) - set(stable_list) - set(overflow_files)
# These could go inline if space available, or to vector store

# 4. Create ephemeral vector store as always
vector_store_id = create_vector_store(overflow_files + new_files + attachments)

# 5. Send to assistant
prompt = format_prompt(inline_files, vector_store_info)
```

### Key Properties

1. **Deterministic**: Once the stable list is set, files never move between inline and vector store
2. **Minimal State**: Just store the list of paths (~50KB for 1000 files)
3. **Efficient**: Only changed files are resent inline
4. **Fast**: Change detection via mtime/size, not expensive hashing
5. **No Compaction Issues**: When assistant's context fills, start new session with new list

## Implementation Details

### State Storage Schema

```sql
-- Minimal state: just the list of files that went inline
CREATE TABLE IF NOT EXISTS stable_inline_lists (
    session_id TEXT PRIMARY KEY,
    inline_paths TEXT NOT NULL,  -- JSON array of paths
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- Track when files were last sent (for change detection)
CREATE TABLE IF NOT EXISTS sent_files (
    session_id TEXT,
    file_path TEXT,
    last_size INTEGER,
    last_mtime INTEGER,
    PRIMARY KEY (session_id, file_path)
);
```

### File Change Detection

```python
def file_changed_since_last_send(session_id: str, file_path: str) -> bool:
    """Check if file has changed using size/mtime."""
    current_stat = os.stat(file_path)
    last_sent = get_last_sent_info(session_id, file_path)
    
    if not last_sent:
        return True  # Never sent before
    
    return (current_stat.st_size != last_sent.size or 
            current_stat.st_mtime != last_sent.mtime)
```

### Deterministic Sorting

```python
def sort_files_for_stable_list(file_paths: List[str]) -> List[str]:
    """Sort files to maximize useful inline content."""
    file_info = []
    
    for path in file_paths:
        try:
            size = os.path.getsize(path)
            tokens = estimate_tokens(size)  # Rough estimate
            file_info.append((path, size, tokens))
        except:
            continue
    
    # Sort by token count (ascending) then path
    # This puts more small files inline
    file_info.sort(key=lambda x: (x[2], x[0]))
    
    return [path for path, _, _ in file_info]
```

### Main Algorithm

```python
async def build_prompt_with_stable_list(
    context_paths: List[str], 
    attachments: List[str],
    session_id: str,
    model_config: dict
) -> Tuple[str, Optional[str]]:
    """Build prompt using stable-inline list approach."""
    
    stable_list = get_stable_list(session_id)
    
    if not stable_list:
        # First overflow - establish the stable list
        sorted_paths = sort_files_for_stable_list(context_paths)
        
        inline_paths = []
        overflow_paths = []
        budget = calculate_token_budget(model_config)
        
        for path in sorted_paths:
            tokens = count_tokens_for_file(path)
            if tokens <= budget:
                inline_paths.append(path)
                budget -= tokens
            else:
                overflow_paths.append(path)
        
        # Save the stable list
        save_stable_list(session_id, inline_paths)
        stable_list = inline_paths
        
        # Send all inline files on first call
        files_to_send = inline_paths
    else:
        # Subsequent calls - only send changed files
        files_to_send = []
        overflow_paths = []
        
        for path in context_paths:
            if path in stable_list:
                if file_changed_since_last_send(session_id, path):
                    files_to_send.append(path)
                    update_sent_info(session_id, path)
            else:
                overflow_paths.append(path)
    
    # Create ephemeral vector store for overflow + attachments
    vector_store_id = None
    if overflow_paths or attachments:
        vector_store_id = create_vector_store(overflow_paths + attachments)
    
    # Format the prompt
    prompt = format_prompt_with_files(files_to_send, vector_store_id)
    
    return prompt, vector_store_id
```

### Reset Mechanism

```python
def reset_stable_list(session_id: str):
    """Reset the stable list for cases where the split becomes suboptimal."""
    delete_stable_list(session_id)
    delete_sent_files_info(session_id)
```

## Trade-offs

### Advantages

1. **Truly Deterministic**: Files never jump between inline and vector store
2. **Minimal State**: ~50KB per session (just path lists)
3. **No Duplication**: Unchanged files aren't resent
4. **Fast**: Only stat() calls for change detection, no full file reads
5. **Simple**: No complex diff logic or content hashing
6. **No Compaction Issues**: Assistants have fixed context windows

### Limitations

1. **Frozen Split**: The initial inline/overflow decision can't adapt to changing file sizes
2. **No Content Hashing**: mtime/size checks could miss some changes (rare in practice)
3. **Reset Needed**: Major refactors might require manual reset of the stable list
4. **Still Recreates Vector Stores**: Each call creates new vector store (inherent constraint)

### Accepted Behaviors

1. **Initial Sort Matters**: File ordering on first overflow determines permanent placement
2. **New Files**: Files added after initial overflow typically go to vector store
3. **Session Ends at Limit**: When assistant's context fills, must start new session
4. **Manual Reset Available**: Users can reset suboptimal splits if needed

## Migration Plan

### Phase 1: Add Stable List Tracking
1. Add `stable_inline_lists` table
2. Add `sent_files` table for change tracking
3. Keep existing behavior but start recording stable lists

### Phase 2: Implement Deduplication
1. Modify `build_prompt` to check stable list
2. Skip unchanged files that were previously sent
3. Monitor token usage reduction

### Phase 3: Cleanup
1. Remove any old hash-based or diff-based code
2. Simplify prompt builder logic
3. Add reset command for users

### Rollback Plan
- Feature flag: `enable_stable_inline_list`
- If issues arise, disable flag to revert to full resend
- Tables remain harmless if unused

## Success Metrics

1. **Token Usage**: 50-90% reduction in context tokens for multi-turn sessions
2. **Predictability**: 0 instances of files moving between inline/vector store
3. **Storage**: <100KB per session even for large codebases
4. **Performance**: No increase in prompt building time (stat is fast)

## Example Scenarios

### Scenario 1: Typical Development Session

```
Turn 1: context=["/src"] (50 files, 180k tokens)
- 40 files (120k) → inline (saved to stable list)
- 10 files (60k) → vector store

Turn 2: Modified 3 files
- 3 changed files → sent inline
- 37 unchanged files → skipped
- 10 files → vector store (recreated)
Result: Only 3 files sent instead of 50

Turn 3: Added "/tests" (20 new files)
- 0 files from stable list → sent (none changed)
- 40 files from stable list → skipped
- 10 + 20 files → vector store
Result: Massive token savings
```

### Scenario 2: Context Window Fills

```
Turns 1-15: Progressive development
- Stable list maintains consistency
- Token usage optimized

Turn 16: Assistant reports "context window full"
- Start new session: "implement-auth-v2"
- New stable list created
- Fresh context window
```

## Conclusion

The stable-inline list approach solves both core problems:

1. **Overflow predictability**: Files stay in their assigned location throughout the session
2. **Context duplication**: Only changed files are resent

It does so while respecting all constraints:
- Vector stores remain ephemeral (security)
- Minimal persistent state (~50KB/session)
- No background workers needed
- No complex logic that could fail

The solution is simple, predictable, and implementable with minimal changes to the existing codebase.
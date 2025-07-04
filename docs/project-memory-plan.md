# Project Memory System - Current State & Plan

*Last Updated: 2025-06-24*

## Current Implementation Status

The project memory system is **partially implemented** with significant architectural improvements over the original plan:

### What's Working Now
1. **Conversation Memory Storage** - AI consultations are automatically summarized and stored in vector stores
2. **Session Persistence** - Multi-turn conversations maintain state via SQLite-backed session cache
3. **Memory Search** - `search_project_memory` function allows searching across all memory stores
4. **Attachment Isolation** - Temporary files are kept in ephemeral vector stores, deleted after each call
5. **No Pollution** - Project memory remains clean; temporary attachments never contaminate it

### Key Architectural Insight (from O3 analysis)
**Attachments are intentionally isolated!** The system creates temporary vector stores for attachments that are deleted immediately after use. The `search_session_attachments` function provides models with the ability to search these ephemeral attachments during execution, maintaining clean separation from permanent project memory.

## Core Idea

Create an auto-learning memory system that captures the "why" behind code changes by storing AI consultations and git commits in vector stores. This institutional memory is automatically searchable by future AI model calls, enabling them to learn from past decisions, mistakes, and architectural choices.

**Key Insight**: LLMs are both producers (creating summaries) and consumers (searching memories) of this knowledge. The models are intelligent enough to connect conversations to commits using metadata breadcrumbs - no complex correlation needed.

## Architecture: Two-Store Approach (Empirically Validated)

After extensive testing and discussion with o3, we've validated a simple two-store architecture:

### Store 1: Assistant Conversations
- Created **after each tool call** (o3, gemini, gpt-4.1)
- Contains: conversation summary, model used, session context
- Metadata: `session_id`, `branch`, `prev_commit_sha`, `timestamp`

### Store 2: Git Commits
- Created **at commit time** via git hook
- Contains: commit message, diff summary, change context
- Metadata: `commit_sha`, `parent_sha`, `session_id` (if available), `branch`, `timestamp`

### Why This Works (Test Results)

We ran empirical tests with synthetic data that proved:
1. **Metadata connections work** - Found 4-5 connected pairs per query using session_id
2. **Models successfully connect the dots** - Both o3 and gpt-4.1 connected conversations to commits
3. **o3 performed better** - More detailed responses with dates/SHAs (7 citations vs 4)
4. **No explicit correlation needed** - Models use metadata to understand relationships

### Example Retrieval Flow

```python
# When querying, provide BOTH stores
vector_store_ids = [CONVERSATION_STORE_ID, COMMIT_STORE_ID]

# Models receive results from both stores
# They use metadata to connect related documents:
# - Same session_id
# - Matching prev_commit_sha → parent_sha
# - Same branch + close timestamps
```

## Key Design Principles

### 1. Simplicity Over Complexity

- **No placeholders** - Just append documents as they're created
- **No correlation logic** - Let models use metadata to connect dots
- **No updates** - Pure append-only to both stores
- **Trust model intelligence** - They can handle "vaguely semantic matches"

### 2. Metadata is Key

```python
# Conversation metadata
{
    "type": "conversation",
    "session_id": "session-xyz",
    "tool": "chat_with_o3",
    "branch": "feature-auth",
    "prev_commit_sha": "abc123",
    "timestamp": 1737654000
}

# Commit metadata
{
    "type": "commit",
    "commit_sha": "def456",
    "parent_sha": "abc123",
    "session_id": "session-xyz",  # If available from session cache
    "branch": "feature-auth",
    "timestamp": 1737658000,
    "files_changed": ["auth.py"]
}
```

### 3. Store Management (20k limit solution)

**Configuration: `.secondbrain/stores.json`**
```json
{
    "conversation_stores": [
        {"id": "vs_conv_001", "count": 18500, "created": "2024-01-01"},
        {"id": "vs_conv_002", "count": 3421, "created": "2024-06-01"}
    ],
    "commit_stores": [
        {"id": "vs_commit_001", "count": 17200, "created": "2024-01-01"},
        {"id": "vs_commit_002", "count": 2100, "created": "2024-06-01"}
    ],
    "active_conv_index": 1,
    "active_commit_index": 1
}
```

**Key Points:**
- Rollover at 18k documents (safety buffer)
- Query ALL stores from both types
- Monitor join success rate to tune k value
- Archive old stores after branch deletion

### 4. Search Architecture - Intentional Separation

**Key Architecture Decision**: Based on extensive analysis with O3 and Gemini, we maintain **intentional separation** between permanent project memory and ephemeral attachments:

1. **`search_project_memory`** - Searches only permanent knowledge (conversations, commits)
2. **Native attachment search** - Models can search their current attachments via built-in mechanisms
3. **No cross-contamination** - Ephemeral attachments are deleted after each call

**Why This Works**:
- **Prevents laziness** - LLMs must be intentional about what they're searching
- **Maintains quality** - Project memory stays high-signal, no pollution from temporary files
- **Already implemented** - The executor already creates/deletes ephemeral stores correctly

### Current Implementation Details

#### How Attachments Work (Already Implemented)

1. **User provides attachments** → Files that are too large for context
2. **Executor creates ephemeral vector store** → Temporary store for this call only
3. **Model searches via native mechanisms** → Each model has its own way
4. **Executor deletes vector store** → Cleanup happens automatically after call

```python
# In tools/executor.py - this already works!
if attachments:
    vector_store_ids = [vector_store_manager.create(attachment_files)]
    try:
        result = await adapter.generate(prompt, vector_store_ids)
    finally:
        vector_store_manager.delete(vector_store_ids[0])
```

#### Memory Search Implementation

```python
# tools/search_memory.py - SearchMemoryAdapter
class SearchMemoryAdapter(BaseAdapter):
    async def generate(self, prompt, **kwargs):
        query = kwargs.get("query")
        store_types = kwargs.get("store_types", ["conversation", "commit"])
        
        # Get all permanent memory stores
        all_store_ids = self.memory_config.get_all_store_ids()
        
        # Filter by type and search
        results = await self._search_stores(query, store_ids)
        return formatted_results
```

**Key Points**:
- Only searches permanent stores (project-conversations-XXX, project-commits-XXX)
- Never sees ephemeral attachment stores
- Available to all models via `search_project_memory` tool

### 5. Conversation Summarization (Implemented with Gemini Flash)

Conversations are automatically summarized after each tool call:

```python
# memory/conversation.py
async def create_conversation_summary(messages, response, tool_name):
    # Extract just instructions (not inlined context)
    user_components = _extract_message_components(raw_content)
    
    # Use Gemini Flash for intelligent summarization
    adapter = VertexAdapter(model="gemini-2.5-flash")
    summary = await adapter.generate(
        prompt=summarization_prompt,
        temperature=0.3
    )
    
    # Store with metadata
    return formatted_summary_with_metadata
```

**Smart Design Choices**:
1. **XML parsing** to extract instructions without context files
2. **Gemini Flash** for fast, intelligent summarization
3. **Fallback** to structured summary if Gemini unavailable
4. **Actual response content** included in summary (not just template)

### 6. Metadata-Aware Retrieval (o3's recommendation)

```python
def retrieve_context(query, k_conv=40, k_commit=40):
    # Search both stores
    conv_hits = search(CONV_STORE, query, k=k_conv)
    commit_hits = search(COMMIT_STORE, query, k=k_commit)
    
    # Simple metadata join
    conv_by_session = defaultdict(list)
    for conv in conv_hits:
        conv_by_session[conv.metadata["session_id"]].append(conv)
    
    # Build context with paired documents first
    context = []
    for commit in commit_hits:
        session = commit.metadata.get("session_id")
        if session in conv_by_session:
            # Add conversation first, then commit
            context.extend(conv_by_session[session])
        context.append(commit)
    
    # Add remaining conversations
    context.extend(conv_hits)
    return truncate_to_token_budget(context)
```

## Implementation Status

### 1. Git Commit Memory Storage - ✅ Implemented

Both conversation memory and git commits are stored via the following system:

### Git Post-Commit Hook (Implemented)
```python
import os, sqlite3, json, datetime, hashlib, re
from pathlib import Path
from mcp_second_brain.utils.vector_store import get_client

# Configuration
DB = os.getenv("SESSION_DB_PATH", ".mcp_sessions.sqlite3")
CONFIG_PATH = Path(".secondbrain/config.json")
HOURS_LOOKBACK = 2  # Capture sessions from last 2 hours

# Privacy patterns to redact
REDACT_PATTERNS = [
    r'sk-[a-zA-Z0-9]{48}',      # OpenAI keys
    r'AKIA[0-9A-Z]{16}',        # AWS keys
    r'ghp_[a-zA-Z0-9]{36}',     # GitHub tokens
    r'-----BEGIN.*KEY-----',     # Private keys
]

def get_or_create_store():
    """Get existing store ID or create new one"""
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text())
        return config["memory_store_id"]
    
    # Create new store
    client = get_client()
    store = client.vector_stores.create(name="project-memory")
    
    # Save config
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    config = {
        "memory_store_id": store.id,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "last_gc": datetime.datetime.utcnow().isoformat()
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    return store.id

def redact_sensitive(text):
    """Remove sensitive information"""
    for pattern in REDACT_PATTERNS:
        text = re.sub(pattern, '[REDACTED]', text, flags=re.MULTILINE)
    return text

def get_recent_sessions():
    """Get sessions updated in last N hours"""
    cutoff = int(datetime.datetime.now().timestamp()) - (HOURS_LOOKBACK * 3600)
    with sqlite3.connect(DB) as db:
        cur = db.execute(
            "SELECT session_id, response_id FROM sessions WHERE updated_at > ?", 
            (cutoff,)
        )
        return cur.fetchall()

async def store_commit_memory(commit_sha):
    """Store commit information in vector store"""
    # Get commit details
    diff = get_commit_diff(commit_sha)
    message = get_commit_message(commit_sha)
    
    # Summarize with Gemini Flash
    summary = await summarize_commit(message, diff)
    
    # Try to find session_id from recent cache
    session_id = find_recent_session_id()  # Best effort
    
    doc = {
        "content": summary,
        "metadata": {
            "type": "commit",
            "commit_sha": commit_sha,
            "parent_sha": get_parent_sha(commit_sha),
            "branch": get_current_branch(),
            "timestamp": get_commit_timestamp(commit_sha),
            "files_changed": get_changed_files(commit_sha),
            "session_id": session_id  # May be None
        }
    }
    
    upload_to_store(COMMIT_STORE_ID, doc)

# Git hook script
#!/bin/bash
python -m mcp_second_brain.memory.commit
```

### 2. Store Rollover Management

Need to implement the 18k document rollover:

```python
# memory/config.py - MemoryConfig class
def get_active_conversation_store(self):
    store_id, count = self._get_active_store("conversation")
    if count >= self._rollover_limit:  # 18k
        return self._rollover_store("conversation")
    return store_id
```

### 3. Important: No Auto-Attachment Planned

**Design Decision**: Models must explicitly call `search_project_memory` when they need historical context. This prevents:
- Unnecessary searches on every call
- Token waste from irrelevant results  
- Lazy "search everything" behavior

**Rationale** (from O3/Gemini discussion):
- Intentionality in tool use improves result quality
- Prevents cognitive laziness of always searching
- Reduces latency and token usage
- System prompts can guide when to search

## Architectural Improvements (from Reviews)

### From Gemini 2.5 Pro Review

1. **Centralize Auto-Attachment**: Move all auto-attachment logic to ToolExecutor
2. **Extract Search Service**: Create VectorSearchService for code reuse
3. **Parallel Search**: Use asyncio.gather() for concurrent store searches
4. **Better Error Handling**: Don't silently swallow search failures

### From o3-pro Deep Analysis

1. **Performance Optimizations**:
   - Parallelize vector store searches with timeout limits
   - Implement LRU cache for store metadata
   - Deduplicate search results to reduce context
   - Add token counting guards for Gemini prompts

2. **Security Hardening**:
   - Redaction filter for sensitive content in search results
   - Path traversal protection in file gathering
   - Proper error propagation for auth failures

3. **Architectural Patterns**:
   - Extract VectorSearchService with pluggable backends
   - Replace string templates with structured prompt slots
   - Add preprocessing layer for auto-attachment
   - Implement store selection strategies (recency, relevance)

4. **Scalability Considerations**:
   - Don't attach ALL stores - use "active + N recent"
   - Implement per-branch or per-project rollover limits
   - Add metrics for join success rate and query latency
   - Consider eventual consistency for git hook writes

## Production Considerations

### 1. Monitor Key Metrics
- **Join success rate** - What % of queries return paired conv+commit?
- **Query latency** - Should stay under 1s additional
- **Store growth** - Track documents per store
- **Token usage** - Monitor costs

### 2. Tune k Value
- Start with k=40 for each store
- Increase if join rate < 95%
- Balance with token budget

### 3. Handle 20k Rollover
- Create new store at 18k documents
- Keep all stores in query array
- Archive stores from deleted branches

### 4. Lightweight Garbage Collection
- Delete conversations without commits after 90 days
- Combine old entries into quarterly summaries
- Remove docs from non-existent branches

## Empirical Validation Results

We tested the two-store approach with synthetic data:

### Test Setup
- 8 conversations, 7 commits with metadata linking
- Queries requiring connection of reasoning to implementation
- Tested both o3 and gpt-4.1

### Results
1. **Metadata connections worked** - Found 4-5 connected pairs per query
2. **Both models succeeded** - Connected conversations to commits
3. **o3 was superior** - More detailed, included dates/SHAs (7 vs 4 citations)
4. **No correlation needed** - Models used metadata effectively

### Key Success Factors
- Good metadata (session_id, branch, timestamps)
- Semantic search found relevant documents
- Models intelligently used metadata to connect pairs
- Simple append-only approach worked perfectly

## Why This Architecture Works

### 1. Simplicity Wins
- No placeholders or complex correlation
- Pure append-only to both stores
- Let models do the connection work
- Proven by empirical testing

### 2. Two Stores > One Complex Store
- Natural separation of concerns
- Easier to manage and understand
- Can optimize each independently
- No contamination between types

### 3. Metadata Enables Intelligence
- Models can find connections via session_id
- Timestamps allow chronological reasoning
- Branch info provides context
- No prescriptive filtering needed

### 4. Leverages Existing Infrastructure
- OpenAI vector stores already integrated
- Session cache already exists
- Git hooks are standard
- Minimal new code required

## Implementation Timeline

### Phase 1: Core Implementation (2-3 days)
1. Add conversation storage after tool calls
2. Create git post-commit hook
3. Auto-attach stores to OpenAI models
4. Basic configuration management

### Phase 2: Production Readiness (1-2 days)
1. Add store rollover at 18k documents
2. Implement monitoring and metrics
3. Implement unified file_search for Gemini
4. Create garbage collection script
5. Add security filters (redaction, path traversal)

### Phase 3: Optimization (ongoing)
1. Tune k values based on metrics
2. Optimize summarization prompts
3. Add better session correlation
4. Implement archival strategies

## Critical Context: Claude as User

This system is designed with a critical understanding:
- **Claude (via Claude Code)** is the user creating these memories through MCP tool calls
- **The assistant LLMs (o3, Gemini, GPT-4.1)** are the consumers via RAG
- **Human developers** never directly interact with this system

This means:
1. **Summaries over transcripts** - Raw conversations waste tokens and reduce retrieval quality
2. **Automatic operation** - No manual steps, everything happens via tool execution and git hooks
3. **LLM-optimized format** - Structured metadata for precise filtering, not human readability
4. **Unified cross-model memory** - All models access the same memory through the same infrastructure

## Key Architectural Decisions

### 1. Custom Search Tools Only

We **removed** the native file_search tool from OpenAI models and replaced it with two custom tools:
- `search_project_memory` - For searching permanent memory (conversations, commits)
- `search_session_attachments` - For searching ephemeral attachment stores

This ensures:
- Consistent behavior across all models (OpenAI and Gemini)
- Clear separation between permanent and ephemeral data
- Intentional tool selection by models

### 2. Ephemeral vs Permanent Separation

Based on O3's analysis, the system already maintains perfect separation:
- **Permanent**: Managed by MemoryConfig, prefixed with "project-"
- **Ephemeral**: Created per-call by executor, deleted immediately
- **No mixing**: search_project_memory only sees permanent stores

### 3. Intentional Search Strategy

Models must explicitly choose to search memory. This is by design:
- Prevents lazy "always search" behavior
- Reduces unnecessary API calls and tokens
- Encourages thoughtful tool use
- System prompts guide when searching is valuable

### 4. Attachment Search Implementation

The `search_session_attachments` tool is conditionally registered:
- **Context Variable**: Uses Python's contextvars to track current execution's vector stores
- **Tool Registration**: Only added to model's tools when vector_store_ids are provided
- **Execution Flow**:
  1. Executor creates ephemeral vector store from attachments
  2. Sets context variable with vector store IDs
  3. Models receive search_session_attachments tool in their function list
  4. Models can search attachments during execution
  5. Executor cleans up vector store and clears context after execution

### 5. Multi-Turn Considerations

From O3's analysis, if we need attachment reuse across turns:
- Implement in executor with session-based caching
- NOT through a new public API
- Use TTL-based cleanup
- Monitor for store explosion

## Implementation Gaps & Next Steps

### Completed ✓
1. Conversation memory storage with Gemini Flash summarization
2. Session persistence for multi-turn conversations
3. Memory search via search_project_memory
4. Proper attachment isolation (ephemeral stores)
5. XML parsing to exclude context from summaries
6. Attachment search via search_session_attachments tool
7. Conditional tool registration (attachment search only when vector stores exist)

### To Do
1. **Git commit memory storage** - Post-commit hook implementation
2. **Store rollover** - Handle 18k document limit
3. **Cleanup/GC** - Remove old ephemeral stores if any escape
4. **Monitoring** - Track search latency, join rates, token usage
5. **System prompts** - Guide models on when to use search_project_memory

### Won't Do (By Design)
1. **Auto-attachment of memory** - Models must explicitly search
2. **Cross-session attachment persistence** - Keep it simple, delete after use
3. **Unified search across permanent and ephemeral** - Intentional separation promotes better tool use

## Conclusion

The project memory system has evolved from the original plan based on implementation experience and expert analysis:

1. **Functional attachment system** - Implemented search_session_attachments to make attachments actually searchable
2. **More intentional** - Two distinct search tools prevent lazy "search everything" behavior  
3. **Cleaner separation** - No risk of pollution between permanent/ephemeral stores
4. **Consistent across models** - Both OpenAI and Gemini use the same search interface
5. **Empirically validated** - Core concepts proven to work with real tests

The key insight remains: **Trust model intelligence**. With good metadata and clear interfaces, models successfully use the appropriate search tool for their needs.

**Latest Update (2025-06-24)**: After discovering that attachments were non-functional (models couldn't search uploaded files), we implemented the `search_session_attachments` tool. This restored the intended functionality where models can search both permanent project memory and temporary attachments, with intentional separation between the two.
# Project Memory System - Implementation Plan

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

### 4. Gemini Support via Custom Tool

Create a file_search tool for Gemini that queries OpenAI vector stores:

```python
@tool
class GeminiFileSearch(ToolSpec):
    query: str = Route.prompt(pos=0)
    branch_filter: Optional[str] = Route.prompt()
    
    async def execute(self):
        # Use OpenAI client to search vector stores
        client = get_openai_client()
        stores = get_all_project_stores()
        
        results = await client.vector_stores.search(
            vector_store_ids=stores,
            query=self.query,
            filters={"key": "branch", "value": self.branch_filter} if branch_filter else None
        )
        
        # Return formatted results to Gemini
        return format_search_results(results)
```

### 5. Metadata-Aware Retrieval (o3's recommendation)

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

## Minimal Implementation

### 1. After Each Tool Call

```python
# In mcp_second_brain/tools/executor.py
async def store_conversation_memory(session_id, tool_name, messages, response):
    # Summarize with Gemini Flash
    summary = await summarize_conversation(messages, response)
    
    doc = {
        "content": summary,
        "metadata": {
            "type": "conversation",
            "tool": tool_name,
            "session_id": session_id,
            "branch": get_current_branch(),
            "prev_commit_sha": get_current_sha(),
            "timestamp": int(time.time())
        }
    }
    
    upload_to_store(CONVERSATION_STORE_ID, doc)
```

### 2. Git Post-Commit Hook
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
python -m mcp_second_brain.memory.capture_commit
```

### 3. Auto-attach Both Stores

```python
# In mcp_second_brain/tools/executor.py
def get_memory_stores():
    """Get all memory store IDs"""
    config = load_stores_config()
    stores = []
    
    # Add all conversation stores
    for store in config.get("conversation_stores", []):
        stores.append(store["id"])
    
    # Add all commit stores
    for store in config.get("commit_stores", []):
        stores.append(store["id"])
    
    return stores

# In execute() method:
if self.model_name in ["o3", "o3-pro", "gpt-4.1"]:
    memory_stores = get_memory_stores()
    if memory_stores:
        vector_store_ids = vector_store_ids or []
        vector_store_ids.extend(memory_stores)
```

## Production Considerations (from o3)

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
3. Add Gemini file_search tool
4. Create garbage collection script

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
4. **Cross-model memory** - Gemini can learn from o3's insights via the custom file_search tool

## Conclusion

This project memory system elegantly solves the institutional knowledge problem with radical simplicity:

1. **No complex correlation** - Just good metadata and smart models
2. **Empirically validated** - Tested and proven to work
3. **Minimal implementation** - ~200 lines of code total
4. **Zero friction** - Works automatically in the background

The key insight from our testing: **We don't need to be prescriptive**. Models are intelligent enough to connect conversations to commits using metadata breadcrumbs. The simpler two-store approach outperforms complex correlation systems by trusting in model capabilities.

As o3 concluded: "The empirical test confirms the two-store pattern works; placeholders can be dropped."
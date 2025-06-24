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

### 4. Unified File Search Infrastructure

**Key Architecture Decision**: Both OpenAI and Gemini models expose the exact same `file_search` function interface, matching OpenAI's `file_search.msearch` specification.

#### OpenAI's file_search.msearch Interface

```typescript
// From o3's description:
namespace file_search {
  // Issues multiple queries to a search over the file(s) uploaded by the user
  type msearch = (_: {
    queries?: string[],  // Max 5 queries
  }) => any;
}
```

#### How It Works

1. **Same Interface**: Both model families use the `attachments` parameter
2. **OpenAI Models**: Attachments → vector_store_ids → native file_search.msearch
3. **Gemini Models**: Attachments → vector_store_ids → file_search_msearch function (via Gemini function calling)

#### Implementation for Gemini

```python
# In vertex_file_search.py - matching OpenAI's interface
class GeminiFileSearch:
    def __init__(self, vector_store_ids: List[str]):
        self.vector_store_ids = vector_store_ids
    
    async def msearch(self, queries: Optional[List[str]] = None) -> Dict[str, Any]:
        """Issues multiple queries to search over files.
        
        This matches OpenAI's file_search.msearch signature exactly:
        - Takes optional queries array (max 5)
        - Returns search results with citation markers
        """
        if not queries or not self.vector_store_ids:
            return {"results": []}
        
        # Limit to 5 queries max (same as OpenAI)
        queries = queries[:5]
        
        # Search all stores with all queries in parallel
        all_results = await self._parallel_search(queries)
        
        # Format results to match OpenAI's structure
        formatted_results = []
        for i, result in enumerate(all_results[:20]):
            formatted_results.append({
                "text": result['content'],
                "metadata": {
                    "file_name": result['file_name'],
                    "score": result['score'],
                    **result['metadata']
                },
                "citation": f"<source>{i}</source>"  # Citation marker
            })
        
        return {"results": formatted_results}

# Function declaration for Gemini
FILE_SEARCH_DECLARATION = {
    "name": "file_search_msearch",  # Flattened namespace
    "description": (
        "Issues multiple queries to search over files and vector stores. "
        "Use this to find information in uploaded documents or project memory."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Array of search queries (max 5). Include the user's "
                    "original question plus focused queries for key terms."
                ),
                "maxItems": 5
            }
        },
        "required": []  # queries is optional, matching OpenAI
    }
}
```

#### What Happens at Runtime

1. **User Query**: "What authentication changes were made?"
2. **Executor**: Passes prompt + vector_store_ids to adapter
3. **OpenAI Path**: 
   - Sends vector_store_ids with request
   - OpenAI calls file_search.msearch({queries: ["authentication changes", ...]})
   - Native implementation searches and returns results with citations
4. **Gemini Path**:
   - Registers file_search_msearch function with Gemini
   - Gemini analyzes prompt and calls file_search_msearch({queries: ["What authentication changes were made?", "authentication changes", "auth modifications"]})
   - Our function queries same OpenAI vector stores
   - Returns results in identical format with citation markers
   - Gemini incorporates results and citations in response

#### Key Implementation Details

1. **Multiple Queries**: Following OpenAI's pattern, models typically send:
   - The user's original question (for context)
   - 2-4 focused queries for specific terms
   - Max 5 queries total

2. **Citation Format**: Results include `<source>N</source>` markers that models weave into responses

3. **Parallel Search**: All queries × all stores searched concurrently with timeout

4. **Deduplication**: Identical results across queries are merged

#### Key Benefits

1. **Exact Interface Match**: Same function signature as OpenAI's file_search.msearch
2. **Model Autonomy**: Models decide when/what to search
3. **Unified Backend**: Same vector stores, same search API
4. **Clean Architecture**: Pure function calling, no prompt manipulation

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
python -m mcp_second_brain.memory.commit
```

### 3. Auto-attach for ALL Models

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

# In execute() method - for ALL models:
if settings.memory_enabled:
    memory_stores = get_memory_stores()
    if memory_stores:
        vector_store_ids = vector_store_ids or []
        vector_store_ids.extend(memory_stores)
        
        # OpenAI: passes to native file_search
        # Gemini: VertexMemoryAdapter handles search and injection
```

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

## Key Implementation Insight: Unified File Search

The breakthrough realization is that we implement the SAME `file_search` function for all models:

1. **One Function Name**: All models expose a function called `file_search`
2. **One Vector Store Backend**: All searches go through OpenAI's vector store API
3. **Model-Specific Implementation**:
   - OpenAI: Built-in file_search that queries their vector stores
   - Gemini: We provide a file_search function that queries the same stores
4. **Transparent Memory Access**: Auto-attachment works identically for all models

### Critical Understanding: Function Calling, Not Prompt Injection

For Gemini:
- We register a `file_search_msearch` function matching OpenAI's spec
- Gemini decides when to call it and what queries to send
- Gemini typically sends multiple queries (like o3 does):
  - User's original question
  - Focused keyword searches
  - Alternative phrasings
- The SDK handles the function call/response cycle automatically
- Results include citation markers that Gemini weaves into responses

### Implementation Principles

1. **Exact Function Match**: Our file_search_msearch has the same signature as OpenAI's file_search.msearch
2. **Behavioral Parity**: Multi-query search, citation markers, parallel execution
3. **No Custom Logic**: Models decide everything - when to search, what to search for
4. **Unified Storage**: All models search the same OpenAI vector stores

This ensures true parity: a user switching between o3 and Gemini gets identical search capabilities with the same project memory access.

## Conclusion

This project memory system elegantly solves the institutional knowledge problem with radical simplicity:

1. **No complex correlation** - Just good metadata and smart models
2. **Empirically validated** - Tested and proven to work
3. **Minimal implementation** - ~200 lines of code total
4. **Zero friction** - Works automatically in the background

The key insight from our testing: **We don't need to be prescriptive**. Models are intelligent enough to connect conversations to commits using metadata breadcrumbs. The simpler two-store approach outperforms complex correlation systems by trusting in model capabilities.

As o3 concluded: "The empirical test confirms the two-store pattern works; placeholders can be dropped."
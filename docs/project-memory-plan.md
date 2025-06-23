# Project Memory System - Implementation Plan

## Core Idea

Create an auto-learning memory system that captures the "why" behind code changes by linking AI consultations (Second Brain conversations) with git commits. This institutional memory is automatically searchable by future AI model calls, enabling them to learn from past decisions, mistakes, and architectural choices.

**Key Insight**: LLMs are both producers (creating summaries) and consumers (searching memories) of this knowledge. OpenAI's built-in `file_search` tool handles retrieval automatically - we just need to populate a vector store with the right content.

## Architecture Evolution

### Initial Approach: Branch-Specific Stores (Rejected)
```
main branch → vs_main_store
feature-auth → vs_feature_store
feature-api → vs_api_store
```

**Problems identified by o3:**
- Store explosion (hundreds of stores from CI/dependabot branches)
- No garbage collection for deleted branches
- Cross-branch contamination when attaching multiple stores
- 20k file limit only partially solved
- Git config storage is local-only

### Final Architecture: Single Store with Metadata Filtering

Use ONE persistent OpenAI vector store with rich metadata to enable precise filtering:

```python
# Memory document structure
{
    "content": "Session summary + git diff analysis",
    "metadata": {
        "branch": "feature-auth",
        "commit_sha": "abc123",
        "parent_sha": "def456",
        "session_id": "session-xyz",
        "timestamp": "2024-01-23T10:00:00Z",
        "files_changed": ["auth.py", "login.js"],
        "doc_hash": "sha256_hash"  # For deduplication
    }
}

# Query with metadata filtering
tools=[{
    "type": "file_search",
    "vector_store_ids": [PROJECT_MEMORY_STORE],
    "filters": {
        "or": [
            {"key": "branch", "value": "main"},
            {"key": "branch", "value": current_branch}
        ]
    }
}]
```

## Key Innovations

### 1. Automatic Session Correlation

Instead of manual Session-ID in commit messages, we use a two-phase placeholder system:

**Phase 1: During chat_with_xyz() call**
```python
# Create placeholder with metadata
placeholder_key = f"latest_{branch}_{int(time.time())}_{random.randint(1000,9999)}"
placeholder_doc = {
    "content": "[Placeholder - awaiting commit]",
    "metadata": {
        "placeholder": True,
        "prev_commit_sha": current_git_head(),
        "branch": current_branch(),
        "chat_start": datetime.utcnow().isoformat(),
        "session_id": session_id
    }
}
# Store placeholder in vector store
```

**Phase 2: Post-commit hook**
```python
# Find matching placeholder
prev_sha = get_previous_commit_sha()
placeholders = search_vector_store(
    filters={
        "and": [
            {"key": "placeholder", "value": True},
            {"key": "prev_commit_sha", "value": prev_sha}
        ]
    }
)
# Update placeholder with real content and commit SHA
```

### 2. Vector Store Chaining (20k limit solution)

Maintain multiple vector stores with automatic rollover:

**Configuration: `.secondbrain/stores.json`**
```json
{
    "stores": [
        {"id": "vs_project_001", "count": 19743, "created": "2024-01-01"},
        {"id": "vs_project_002", "count": 3421, "created": "2024-06-01"}
    ],
    "active_index": 1
}
```

**Auto-rollover logic:**
```python
def get_active_store():
    config = load_stores_config()
    active = config["stores"][config["active_index"]]
    
    if active["count"] > 18000:  # Leave buffer before 20k
        # Create new store
        new_store = create_vector_store(f"project-memory-{len(config['stores'])+1}")
        config["stores"].append({
            "id": new_store.id,
            "count": 0,
            "created": datetime.utcnow().isoformat()
        })
        config["active_index"] = len(config["stores"]) - 1
        save_stores_config(config)
        return new_store.id
    
    return active["id"]

# When querying, provide ALL stores
vector_store_ids = [store["id"] for store in config["stores"]]
```

### 3. Gemini Support via Custom Tool

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

### 4. Enhanced Metadata with Chronology

```python
metadata = {
    # Identity
    "commit_sha": "abc123",
    "parent_sha": "def456", 
    "branch": "feature-auth",
    "session_id": "session-xyz",
    
    # Chronology (sortable integers)
    "git_time": 1737654321,      # Commit timestamp (epoch)
    "session_time": 1737654000,   # Chat end timestamp (epoch)
    "message_index": 0,           # Order within session
    
    # Search optimization
    "files_changed": ["auth.py", "login.js"],
    "doc_hash": "sha256_abc",     # Deduplication
    "placeholder": False          # Correlation state
}
```

## Implementation Details

### 1. Configuration Storage
Store shared configuration in `.secondbrain/config.json` (committed to repo):
```json
{
    "memory_store_id": "vs_project_abc123",
    "created_at": "2024-01-20T10:00:00Z",
    "last_gc": "2024-01-20T10:00:00Z"
}
```

### 2. Git Hook Script (`scripts/capture_memory.py`)
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

def find_and_update_placeholders(prev_sha, commit_info):
    """Find placeholders matching previous SHA and update them"""
    client = get_client()
    store_id = get_active_store()
    
    # Search for matching placeholders
    results = client.vector_stores.files.search(
        vector_store_id=store_id,
        query="placeholder",
        filters={
            "and": [
                {"type": "eq", "key": "placeholder", "value": True},
                {"type": "eq", "key": "prev_commit_sha", "value": prev_sha}
            ]
        }
    )
    
    for result in results:
        # Get session from metadata
        session_id = result.metadata.get("session_id")
        if not session_id:
            continue
            
        # Create full memory document
        content = create_memory_content(session_id, commit_info)
        
        # Update the placeholder file
        client.vector_stores.files.update(
            vector_store_id=store_id,
            file_id=result.id,
            content=content,
            metadata={
                **result.metadata,
                "placeholder": False,
                "commit_sha": commit_info['sha'],
                "git_time": int(os.popen(f"git show -s --format=%ct {commit_info['sha']}").read().strip()),
                "files_changed": get_changed_files(commit_info['sha'])
            }
        )

def check_duplicate(store_id, doc_hash):
    """Check if document already exists"""
    # Would use vector store search API with metadata filter
    # Return True if doc_hash already exists
    return False

def main():
    sessions = get_recent_sessions()
    if not sessions:
        print("No recent sessions to capture")
        return
    
    store_id = get_or_create_store()
    client = get_client()
    
    # Get git info
    sha = os.popen("git rev-parse HEAD").read().strip()
    parent = os.popen("git rev-parse HEAD~1").read().strip() or "root"
    branch = os.popen("git branch --show-current").read().strip()
    
    commit_info = {
        "sha": sha,
        "parent": parent,
        "branch": branch
    }
    
    # Create memory documents
    files_to_upload = []
    for session_id, _ in sessions:
        doc = create_memory_document(session_id, commit_info)
        
        # Skip if duplicate
        if check_duplicate(store_id, doc["metadata"]["doc_hash"]):
            print(f"Skipping duplicate for session {session_id}")
            continue
        
        # Create temp file
        tmp = Path(f"/tmp/memory_{sha}_{session_id}.json")
        tmp.write_text(json.dumps(doc))
        files_to_upload.append(tmp.open("rb"))
    
    # Upload to vector store
    if files_to_upload:
        client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=store_id,
            files=files_to_upload
        )
        print(f"Added {len(files_to_upload)} memories to project store")
    
    # Cleanup
    for f in files_to_upload:
        f.close()

if __name__ == "__main__":
    main()
```

### 3. Auto-attach in ToolExecutor

Modify `mcp_second_brain/tools/executor.py`:

```python
def get_project_memory_store():
    """Get project memory store ID if it exists"""
    config_path = Path(".secondbrain/config.json")
    if config_path.exists():
        config = json.loads(config_path.read_text())
        return config.get("memory_store_id")
    return None

# In execute() method:
if self.model_name in ["o3", "o3-pro", "gpt-4.1"]:
    memory_store = get_project_memory_store()
    if memory_store:
        vector_store_ids = vector_store_ids or []
        vector_store_ids.append(memory_store)
        
        # Add branch-specific filter
        current_branch = os.popen("git branch --show-current").read().strip()
        if hasattr(tool_instance, 'filters'):
            tool_instance.filters = {
                "or": [
                    {"type": "eq", "key": "branch", "value": "main"},
                    {"type": "eq", "key": "branch", "value": current_branch}
                ]
            }
```

### 4. Garbage Collection (`scripts/gc_memory.py`)

```python
def garbage_collect_old_branches():
    """Remove memories from deleted branches"""
    active_branches = set(
        os.popen("git branch -a").read().strip().split('\n')
    )
    
    # Query vector store for all unique branches
    # Delete documents where branch not in active_branches
    
    # Update last_gc timestamp
    config = json.loads(CONFIG_PATH.read_text())
    config["last_gc"] = datetime.datetime.utcnow().isoformat()
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
```

## Testing Strategy

### 1. Unit Tests

```python
def test_redaction():
    """Ensure sensitive data is removed"""
    text = "My API key is sk-1234567890abcdef"
    redacted = redact_sensitive(text)
    assert "sk-" not in redacted
    assert "[REDACTED]" in redacted

def test_deduplication():
    """Ensure duplicate documents aren't uploaded"""
    doc1 = create_memory_document("session1", commit_info)
    doc2 = create_memory_document("session1", commit_info)
    assert doc1["metadata"]["doc_hash"] == doc2["metadata"]["doc_hash"]
```

### 2. Integration Tests

```python
def test_branch_isolation():
    """Ensure branch filtering works correctly"""
    # Upload memory for main branch
    upload_memory("main", "Uses JWT authentication")
    
    # Upload memory for feature branch
    upload_memory("feature-oauth", "Uses OAuth authentication")
    
    # Query with branch filter
    response = query_with_filter("How does auth work?", branch="feature-oauth")
    
    # Should only see OAuth, not JWT
    assert "OAuth" in response
    assert "JWT" not in response
```

### 3. End-to-End Validation

**A/B Test Protocol:**
- Week 1: Baseline (no memory system)
- Week 2: With memory system enabled
- Track metrics:
  - Time to resolve issues
  - Number of follow-up questions
  - Developer satisfaction ratings

**Success Metrics:**
1. **Context Precision**: >95% of retrieved chunks match query branch
2. **Deduplication Rate**: <5% duplicate documents
3. **Query Latency**: <1s additional latency
4. **Storage Efficiency**: <10MB per 1000 commits
5. **Developer Value**: >80% report "helpful context"

## Key Design Decisions

### 1. Why OpenAI Vector Stores Only?
- Zero new infrastructure required
- Built-in semantic search with file_search tool
- Handles retrieval automatically
- Scales to millions of documents

### 2. Why Single Store with Metadata?
- Avoids store explosion problem
- Enables sophisticated filtering
- Simplifies garbage collection
- Better cost control

### 3. Why Git Hooks?
- Natural integration point
- Captures context at commit time
- No changes to developer workflow
- Works with any git client

### 4. Why Include Session Cache?
- Links conversations to code changes
- Captures the "why" behind decisions
- Already exists in our infrastructure
- Provides rich context for summaries

## Limitations and Future Work

### Current Limitations (Addressed)
1. ~~Only works with OpenAI models~~ → Gemini support via custom file_search tool
2. ~~20k file limit per store~~ → Vector store chaining (file_search accepts arrays)
3. ~~Requires manual session correlation~~ → Automatic correlation via placeholder system
4. ~~No chronological ordering~~ → git_time and session_time metadata fields

### Future Enhancements
1. Local vector store mirror for Gemini support
2. Hierarchical stores for very large projects
3. Automatic session correlation via IDE integration
4. Memory document versioning and updates
5. Cross-project memory federation

### 5. Placeholder Creation During Chat

Add to `mcp_second_brain/tools/executor.py` after each tool execution:

```python
async def create_placeholder_memory(session_id: str, tool_name: str, result: str):
    """Create placeholder memory entry after successful tool execution"""
    if tool_name not in ["chat_with_o3", "chat_with_gemini25_pro", "chat_with_gpt4_1"]:
        return
        
    # Get current git state
    branch = os.popen("git branch --show-current").read().strip()
    prev_sha = os.popen("git rev-parse HEAD").read().strip()
    
    # Create placeholder
    placeholder_key = f"latest_{branch}_{int(time.time())}_{random.randint(1000,9999)}"
    
    placeholder_doc = {
        "content": f"[Placeholder - Session {session_id}]\nTool: {tool_name}\nAwaiting commit...",
        "metadata": {
            "placeholder": True,
            "prev_commit_sha": prev_sha,
            "branch": branch,
            "session_id": session_id,
            "chat_start": datetime.utcnow().isoformat(),
            "tool_name": tool_name
        }
    }
    
    # Upload to active store
    store_id = get_active_store()
    await upload_memory_doc(store_id, placeholder_key, placeholder_doc)
```

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

This project memory system elegantly solves the institutional knowledge problem with minimal complexity:

1. **Automatic correlation** - Placeholder system links conversations to commits without manual intervention
2. **Unlimited scale** - Vector store chaining handles the 20k file limit transparently
3. **Universal access** - All models (including Gemini) can search the knowledge base
4. **Zero friction** - Works automatically in the background during normal Claude Code usage

The key insight is that we're creating an "AI-to-AI" memory layer where Claude's conversations with assistant models are automatically captured, correlated with code changes, and made searchable for future interactions. This turns every consultation into lasting institutional knowledge without disrupting the development workflow.
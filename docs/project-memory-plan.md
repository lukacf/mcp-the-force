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

def create_memory_document(session_id, commit_info):
    """Create a memory document with metadata"""
    # In real implementation, would extract conversation from session cache
    # and summarize with Gemini Flash
    
    content = f"""
## Session: {session_id}

### Context
[Conversation summary would go here]

### Code Changes
Commit: {commit_info['sha']}
Branch: {commit_info['branch']}
Parent: {commit_info['parent']}

[Git diff summary would go here]

### Key Decisions
[Extracted reasoning and decisions]
"""
    
    # Redact sensitive info
    content = redact_sensitive(content)
    
    # Create document with metadata
    doc_hash = hashlib.sha256(content.encode()).hexdigest()
    
    return {
        "content": content,
        "metadata": {
            "branch": commit_info['branch'],
            "commit_sha": commit_info['sha'],
            "parent_sha": commit_info['parent'],
            "session_id": session_id,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "doc_hash": doc_hash
        }
    }

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

### Current Limitations
1. Only works with OpenAI models (Gemini can't use vector stores)
2. 20k file limit per store (years of commits for most projects)
3. Requires manual session correlation (via commit message)
4. No versioning of memory documents

### Future Enhancements
1. Local vector store mirror for Gemini support
2. Hierarchical stores for very large projects
3. Automatic session correlation via IDE integration
4. Memory document versioning and updates
5. Cross-project memory federation

## Conclusion

This project memory system provides a simple, powerful way to capture institutional knowledge with minimal infrastructure changes. By leveraging OpenAI's vector stores as the sole storage system and using git hooks for automatic capture, we create a self-maintaining knowledge base that grows with the project and improves AI assistance over time.

The key insight is that we're not building a complex knowledge management system - we're simply capturing what already exists (conversations and code changes) and making it searchable by future AI interactions. The ~80 lines of implementation code deliver outsized value by turning ephemeral knowledge into persistent, searchable memory.
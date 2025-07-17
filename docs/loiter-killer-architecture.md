# Loiter Killer Service - Implementation Status

## Overview

A lightweight service that prevents OpenAI vector store limit errors by managing store lifecycle across ephemeral MCP server instances.

## Current Implementation Status (2025-01-17)

### ✅ Completed
- **TDD Implementation**: 7 comprehensive tests written first, then implementation
- **Core Service**: ~300 lines of Python using FastAPI
- **All Endpoints Working**:
  - `GET /health` - Health check
  - `POST /session/{id}/acquire` - Get or create vector store
  - `POST /session/{id}/files` - Track files for cleanup
  - `POST /session/{id}/renew` - Extend lease by 1 hour
  - `POST /cleanup` - Manual cleanup trigger
- **SQLite Database**: Sessions and files tracking
- **Background Cleanup**: Runs every 5 minutes
- **Test Mode**: Mock OpenAI client for testing

### ✅ OpenAI Connection Status

**Fixed**: The service now properly validates and requires the OpenAI API key.

```python
# Current code:
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("ERROR: OPENAI_API_KEY environment variable is required")
    print("Please set it before starting the service:")
    print("  export OPENAI_API_KEY=your-api-key")
    raise ValueError("OPENAI_API_KEY environment variable is required")
client = AsyncOpenAI(api_key=api_key)
```

**Deletion Strategy**: 
- Files and vector stores are deleted **sequentially** (not in parallel)
- This is simpler and sufficient for the cleanup use case
- Each file is deleted one by one with error handling
- Failed deletions are logged but don't stop the cleanup process

## Architecture

```
MCP Servers (ephemeral)
    │
    ├─── HTTP (localhost:9876) ───┐
    │                             ▼
    │                    Loiter Killer Service
    │                    ├── SQLite database
    │                    ├── Lease tracking (1hr expiry)
    │                    └── Cleanup loop (5min interval)
    │
    └─── Falls back to creating own stores if service is down
```

## Implementation

### Database (SQLite)
```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    vector_store_id TEXT NOT NULL,
    expires_at INTEGER NOT NULL  -- Unix timestamp
);

CREATE TABLE files (
    file_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL
);
```

### API Endpoints
```
POST   /session/{id}/acquire    # Get or create vector store
POST   /session/{id}/renew      # Extend lease by 1 hour  
POST   /session/{id}/files      # Add files to track
```

### Core Logic
1. Check for existing session → reuse vector store
2. Create new if needed → track in DB
3. Cleanup loop runs every 5 minutes → delete expired

### Error Handling
- If acquire fails → MCP creates its own ephemeral store
- If cleanup fails → retry next cycle
- If service is down → MCP works normally (just less efficient)

## Deployment

### Docker Compose
```yaml
services:
  loiter-killer:
    build: ./loiter-killer
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    ports:
      - "127.0.0.1:9876:9876"
    volumes:
      - ./loiter-killer-data:/data
    restart: unless-stopped
```

### Or Simple Python Process
```bash
python loiter_killer.py
# Runs on localhost:9876
# SQLite DB in ./loiter_killer.db
```

## Integration with MCP

```python
# In MCP server
async def get_vector_store(session_id):
    try:
        # Try loiter killer first
        resp = await httpx.post(f"http://localhost:9876/session/{session_id}/acquire")
        return resp.json()["vector_store_id"]
    except:
        # Fallback: create ephemeral store
        vs = await client.vector_stores.create(name=f"temp_{session_id[:8]}")
        return vs.id
```

## Benefits

- **Stays under limit**: Reuses stores across queries
- **No more orphaned files**: Everything gets cleaned up
- **Simple**: ~200 lines of Python
- **Reliable**: MCP works even if service is down

## Implementation Complete (2025-01-17)

### What Was Implemented

1. **Docker Auto-Start**: The MCP server now automatically starts the Loiter Killer container on startup via `DockerManager` in `server.py`.

2. **VictoriaLogs Integration**: Loiter Killer now logs to the same VictoriaLogs instance as the MCP server for unified observability.

3. **VectorStoreManager Integration**:
   - Added `LoiterKillerClient` to communicate with the service
   - Modified `create()` to use Loiter Killer when `session_id` is provided
   - Tracks all vector stores per session for attachment search
   - Falls back to ephemeral stores if Loiter Killer is unavailable

4. **ToolExecutor Updates**:
   - Passes `session_id` to `VectorStoreManager.create()`
   - Renews lease before long-running operations
   - Maintains backward compatibility with ephemeral pattern

5. **File Deduplication**:
   - Created `vector_store_files.py` for adding files to existing stores
   - Prevents re-uploading files already in the vector store
   - Tracks new file IDs with Loiter Killer

### Key Code Changes

- `server.py`: Added Docker auto-start on MCP startup
- `loiter_killer.py`: Added VictoriaLogs logging
- `vector_store_manager.py`: Complete Loiter Killer integration
- `executor.py`: Pass session_id and renew leases
- `docker-compose.yaml`: Added loiter-killer service
- `utils/docker_manager.py`: Docker container management
- `utils/loiter_killer_client.py`: HTTP client for Loiter Killer
- `utils/vector_store_files.py`: File deduplication utilities

## MCP Integration Plan

### The ROOT CAUSE We're Solving

**OpenAI has a hard limit of 100 vector stores per project**

When you approach this limit (99-100 stores):
- `upload_and_poll()` **hangs indefinitely** - no error, just blocks forever
- MCP server becomes completely unresponsive
- Must manually clean up vector stores to recover

### How This Happens

Every time a user queries with large context that overflows:
```python
# Current flow creates a NEW vector store every time:
if files_overflow_context:
    vs_id = await vector_store_manager.create(files)  # Creates store #1, #2, ... #99
    # After query, tries to delete but often fails
    await vector_store_manager.delete(vs_id)  # Deletion fails/hangs
```

After ~100 queries with large contexts → **HANG at store creation**

### The Solution with Loiter Killer

**REUSE vector stores** instead of creating new ones:
```python
# New flow - reuse stores based on session:
if files_overflow_context:
    # Same files = same session = same vector store
    session_id = hash(file_paths)
    
    # Reuse store #5 instead of creating store #101
    vs_id = await loiter_killer.get_or_create_vector_store(session_id)
    
    # No immediate deletion - Loiter Killer cleans up after 1hr idle
```

**Result**: Stay well below 100 store limit by reusing stores

### Architecture Overview

```
┌─────────────────────────────────────────────────┐
│               MCP Server                        │
│                                                 │
│  1. Check if Loiter Killer is running          │
│  2. Use it for all vector store operations     │
│  3. Fall back to direct OpenAI if unavailable  │
└────────────────────┬────────────────────────────┘
                     │
                     │ HTTP (localhost:9876)
                     ▼
┌─────────────────────────────────────────────────┐
│         Loiter Killer (Docker Container)        │
│                                                 │
│  - Manages vector store lifecycle               │
│  - Tracks files for cleanup                     │
│  - Reuses stores per session                    │
│  - Auto-cleanup after 1 hour                    │
└─────────────────────────────────────────────────┘
```

### Implementation Steps

#### 1. Docker Setup

Create `Dockerfile.loiter_killer`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY loiter_killer.py requirements-loiter.txt ./
RUN pip install -r requirements-loiter.txt
ENV PYTHONUNBUFFERED=1
CMD ["python", "loiter_killer.py"]
```

Add to `docker-compose.yml`:
```yaml
services:
  loiter-killer:
    build:
      context: .
      dockerfile: Dockerfile.loiter_killer
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    ports:
      - "127.0.0.1:9876:9876"
    volumes:
      - ./loiter_killer_data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9876/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

#### 2. Create LoiterKillerClient

`mcp_second_brain/utils/loiter_killer_client.py`:
```python
class LoiterKillerClient:
    def __init__(self):
        self.base_url = "http://localhost:9876"
        self.enabled = self._check_availability()
    
    async def get_or_create_vector_store(self, session_id: str) -> Tuple[str, List[str]]:
        """Get existing or create new vector store for session."""
        if not self.enabled:
            return None, []
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/session/{session_id}/acquire",
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    return data["vector_store_id"], data.get("files", [])
        except Exception as e:
            logger.warning(f"Loiter killer unavailable: {e}")
            self.enabled = False
        
        return None, []
    
    async def track_files(self, session_id: str, file_ids: List[str]):
        """Track files for cleanup."""
        if not self.enabled or not file_ids:
            return
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.base_url}/session/{session_id}/files",
                    json=file_ids,
                    timeout=5.0
                )
        except Exception:
            pass  # Best effort
    
    async def renew_lease(self, session_id: str):
        """Keep session alive during long operations."""
        if not self.enabled:
            return
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.base_url}/session/{session_id}/renew",
                    timeout=5.0
                )
        except Exception:
            pass  # Best effort
    
    def _check_availability(self) -> bool:
        """Check if loiter killer is available."""
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=2.0)
            return response.status_code == 200
        except Exception:
            return False
```

#### 3. Modify VectorStoreManager

Update `vector_store.py`:
```python
class VectorStoreManager:
    def __init__(self, openai_client_factory: OpenAIClientFactory):
        self.client_factory = openai_client_factory
        self.loiter_killer = LoiterKillerClient()
    
    async def create(self, files: List[UploadedFile], session_id: Optional[str] = None) -> str:
        # Generate session ID if not provided
        if not session_id:
            session_id = self._generate_session_id(files)
        
        # Try loiter killer first
        vs_id, existing_files = await self.loiter_killer.get_or_create_vector_store(session_id)
        
        if vs_id:
            # Use existing vector store
            new_files = [f for f in files if f.file_id not in existing_files]
            if new_files:
                # Upload only new files
                await self._add_files_to_store(vs_id, new_files)
                # Track new files
                await self.loiter_killer.track_files(
                    session_id, 
                    [f.file_id for f in new_files]
                )
            return vs_id
        
        # Fallback to current implementation
        return await self._create_direct(files)
    
    def _generate_session_id(self, files: List[UploadedFile]) -> str:
        """Generate deterministic session ID from context."""
        # Use hash of file paths for consistency
        content = "|".join(sorted(f.path for f in files))
        return hashlib.md5(content.encode()).hexdigest()[:16]
```

#### 4. Update Executor

Modify `executor.py` to pass session context:
```python
# In execute_tool_call method
if attachments_vs_id:
    # Extract session ID from conversation context
    session_id = self._get_session_id(tool_input)
    
    # Renew lease during execution
    await self.vector_store_manager.loiter_killer.renew_lease(session_id)
```

### Benefits

1. **Automatic Resource Management**: No manual cleanup needed
2. **Session Continuity**: Reuses vector stores across queries
3. **Docker Isolation**: Clean separation from MCP server
4. **Graceful Fallback**: Works even without loiter killer
5. **Zero Configuration**: Just run docker-compose

### Running Everything

```bash
# Start both MCP server and Loiter Killer
docker-compose up -d

# Or manually:
docker-compose up -d loiter-killer
uv run -- mcp-second-brain

# Check status
docker-compose ps
curl http://localhost:9876/health
```

## Testing

All tests pass:
```bash
# Loiter Killer tests
TEST_MODE=true python -m pytest test_loiter_killer.py -v

# Integration tests
docker-compose up -d loiter-killer
python -m pytest tests/integration/test_vector_store_with_loiter.py
```
# MCP The Force: VictoriaLogs Migration & System Fixes

## Overview

Replace our custom logging solution with VictoriaLogs and fix detrimental changes introduced during the logging system work.

## Part 1: VictoriaLogs Migration

### Why VictoriaLogs?

Our custom logging solution is a maintenance burden:
- 500+ lines of custom Python code (daemon, manager, handlers, HTTP API)
- Complex process management and health checking
- Basic SQL LIKE search vs full-text search

VictoriaLogs provides:
- **14MB single binary** - no dependencies, no complexity
- **Full-text search** with LogsQL query language
- **30-60% disk savings** with columnar compression
- **Loki-compatible** - use standard `logging-loki` handler

### Setup

```bash
# Create volume and run container
docker volume create the-force-logs-data
docker run -d --name victorialogs \
  -p 9428:9428 \
  -v the-force-logs-data:/var/lib/victorialogs \
  victoriametrics/victoria-logs:v1.17.0 \
  -retentionPeriod=7d
```

### Replace Custom Logging Code

**Delete these files:**
- `mcp_the_force/logging/daemon.py`
- `mcp_the_force/logging/daemon_manager.py`
- `mcp_the_force/logging/push_handler.py`
- `mcp_the_force/logging/schema.sql`
- `mcp_the_force/logging/__main__.py`

**Update `mcp_the_force/logging/setup.py`:**

```python
import logging
import os
from logging_loki import LokiHandler
from ..config import get_settings

def setup_logging():
    """Initialize VictoriaLogs-based logging."""
    settings = get_settings()
    
    app_logger = logging.getLogger("mcp_the_force")
    app_logger.setLevel(settings.logging.level)
    app_logger.propagate = False
    
    if app_logger.hasHandlers():
        app_logger.handlers.clear()
    
    if not settings.logging.developer_mode.enabled:
        app_logger.addHandler(logging.NullHandler())
        return
    
    # Use standard logging-loki handler
    loki_handler = LokiHandler(
        url="http://localhost:9428/insert/loki/api/v1/push?_stream_fields=app,instance_id",
        tags={
            "app": "mcp-the-force",
            "instance_id": settings.instance_id,
            "project": os.getenv("MCP_PROJECT_PATH", os.getcwd())
        },
        version="1"
    )
    
    app_logger.addHandler(loki_handler)
    app_logger.info("Logging initialized with VictoriaLogs")
```

**Update `mcp_the_force/adapters/logging_adapter.py`:**

```python
import httpx
from typing import List, Dict, Any

class LoggingAdapter:
    """Query logs from VictoriaLogs using LogsQL."""
    
    def __init__(self, base_url: str = "http://localhost:9428"):
        self.base_url = base_url
        
    async def search_logs(
        self, 
        query: str, 
        level: str = None,
        since: str = "1h",
        project_path: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search logs using VictoriaLogs LogsQL."""
        
        # Build LogsQL query
        filters = []
        if level:
            filters.append(f'level:="{level}"')
        if project_path:
            filters.append(f'project:="{project_path}"')
            
        # Combine filters
        logsql = " AND ".join(filters) if filters else ""
        
        # Add text search
        if query:
            if logsql:
                logsql += f' AND "{query}"'
            else:
                logsql = f'"{query}"'
        
        # Add time filter and limit
        logsql = f'({logsql}) AND _time:{since}' if logsql else f'_time:{since}'
        logsql += f' | limit {limit}'
        
        # Query VictoriaLogs
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/select/logsql/query",
                data={"query": logsql}
            )
            response.raise_for_status()
            
        return response.json()
```

## Part 2: Fixing Detrimental Changes

### 1. Restore Structured Output Validation

**Fix in `mcp_the_force/adapters/openai/flow.py`:**

```python
def _validate_structured_output(self, response_content: str) -> None:
    """Validate structured output against schema."""
    if not self.structured_output_schema:
        return
        
    try:
        import jsonschema
        parsed = json.loads(response_content)
        jsonschema.validate(parsed, self.structured_output_schema)
    except jsonschema.ValidationError as e:
        raise AdapterException(
            f"Response does not match requested schema: {str(e)}",
            error_category=ErrorCategory.INVALID_RESPONSE
        )
    except json.JSONDecodeError as e:
        raise AdapterException(
            f"Response is not valid JSON: {str(e)}",
            error_category=ErrorCategory.INVALID_RESPONSE
        )
```

**Similar fix for `mcp_the_force/adapters/vertex/adapter.py`**

### 2. Restore Memory Storage Timeout

**Fix in `mcp_the_force/tools/executor.py`:**

```python
# Restore original 120-second timeout for vector store operations
MEMORY_STORAGE_TIMEOUT = 120.0  # Restored from 30.0

# Fix divergent test/production paths
if self._background_tasks is not None:
    # Always create proper asyncio.Task for both test and production
    task = asyncio.create_task(
        store_conversation_memory(
            session_id=session_id,
            adapter_name=adapter_name,
            instructions=instructions,
            output=output,
            context_paths=context,
            settings=self.settings,
        )
    )
    self._background_tasks.append(task)
```

### 3. Restore Specific Error Handling in Vertex Adapter

**Fix in `mcp_the_force/adapters/vertex/adapter.py`:**

```python
try:
    response = await self._generate_async(...)
except google.api_core.exceptions.ResourceExhausted as e:
    raise AdapterException(
        "Rate limit exceeded. Please try again later.",
        error_category=ErrorCategory.RATE_LIMIT,
        original_error=e
    )
except google.api_core.exceptions.InvalidArgument as e:
    raise AdapterException(
        f"Invalid request: {str(e)}",
        error_category=ErrorCategory.INVALID_REQUEST,
        original_error=e
    )
except google.api_core.exceptions.ServiceUnavailable as e:
    raise AdapterException(
        "Service temporarily unavailable. Please retry.",
        error_category=ErrorCategory.TRANSIENT_ERROR,
        original_error=e
    )
except Exception as e:
    logger.error(f"Unexpected error: {type(e).__name__}: {str(e)}")
    raise
```

### 4. Restore File Verification in Vector Store

**Fix in `mcp_the_force/utils/vector_store.py`:**

```python
async def create_vector_store(paths: List[str], ...) -> VectorStoreInfo:
    """Create vector store with proper file verification."""
    
    # Pre-verify all files exist and are readable
    verified_files = []
    for path in file_paths:
        if await aiofiles.os.path.exists(path):
            try:
                stat = await aiofiles.os.stat(path)
                if stat.st_size > 0:
                    verified_files.append(path)
            except Exception as e:
                logger.warning(f"Skipping inaccessible file {path}: {e}")
        else:
            logger.warning(f"File not found: {path}")
    
    if not verified_files:
        raise ValueError("No accessible files to upload")
    
    # Upload verified files
    with client.beta.vector_stores.file_batches.upload_and_poll(
        vector_store_id=vector_store.id,
        files=[open(path, "rb") for path in verified_files],
    ) as batch:
        logger.info(f"Uploaded {batch.file_counts.completed} files")
```

## Dependencies

Add to `pyproject.toml`:
```toml
logging-loki = "^0.3.1"
```

## Conclusion

This replaces our NIH (Not Invented Here) custom logging solution with a standard tool and fixes the detrimental changes we introduced. Result: simpler, more maintainable codebase with better logging capabilities.
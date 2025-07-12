# MCP Second Brain Logging System Specification

## Overview

This document specifies a comprehensive logging system for the MCP Second Brain project that addresses the unique challenges of debugging distributed MCP servers in Docker-in-Docker (DinD) environments.

## Requirements

### Core Requirements

1. **MCP-Started Service**: The logging service must be started by the MCP server process itself, not as an external service
2. **Docker-in-Docker Support**: Must work seamlessly in nested Docker containers used for E2E testing
3. **No Background Daemons**: Following the SQLite pattern - start with the process, die with the process
4. **Persistent Storage**: Logs must survive container restarts and be stored on the native host
5. **MCP Protocol Compliance**: Cannot use stdout (corrupts MCP stdio protocol)
6. **Multi-Instance Support**: Handle multiple concurrent MCP server instances without conflicts
7. **Zero Configuration**: Must work out-of-the-box for regular users
8. **Developer-Only Feature**: Logging system should be opt-in for developers only

### Functional Requirements

1. **Aggregated Logging**: All MCP instances write to a single, queryable log store
2. **High Performance**: Minimal impact on MCP server performance
3. **Programmatic Access**: Claude must be able to query logs via MCP tools
4. **Network-Based**: Use network communication (not shared files) for Docker compatibility
5. **Graceful Degradation**: If logging fails, MCP server must continue operating

### Technical Constraints

1. **Port-Based Communication**: Always use `localhost:4711` with port forwarding
2. **SQLite Storage**: Use SQLite for persistent, queryable storage
3. **ZeroMQ Transport**: Use ZMQ for high-performance, decoupled messaging
4. **Python 3.10+**: Must work with existing Python environment

## Architecture

### Components

```
┌─────────────────┐     ZMQ PUSH      ┌──────────────────┐
│   MCP Server 1  │ ─────────────────> │                  │
└─────────────────┘                    │                  │
                                       │   ZMQ Log Server │     SQLite
┌─────────────────┐     ZMQ PUSH      │   (First MCP)    │ ──────────>  .mcp_logs.sqlite3
│   MCP Server 2  │ ─────────────────> │                  │
└─────────────────┘                    │  localhost:4711  │
                                       │                  │
┌─────────────────┐     ZMQ PUSH      │                  │
│ Docker Container│ ─────────────────> │                  │
└─────────────────┘                    └──────────────────┘
```

### Port Forwarding Strategy

```
Native:
  MCP → localhost:4711 → ZMQ Server

Docker:
  docker run -p 4711:4711 -e MCP_PROJECT_PATH=$(PWD)
  Container → localhost:4711 → Host's localhost:4711

Docker-in-Docker:
  Outer: docker run -p 4711:4711 -e MCP_PROJECT_PATH=$(PWD)
  Inner: network_mode: "service:test-runner"
  All containers → localhost:4711 → Native ZMQ Server
```

### Environment Variables

- `MCP_PROJECT_PATH`: Canonical native project path (set by host, passed through Docker layers)
  - Native: Not needed, uses `os.getcwd()`
  - Docker/DiD: Set to actual host path (e.g., `/Users/luka/src/cc/mcp-second-brain`)
  - Ensures all logs from same project have consistent `project_cwd` value

## Implementation Plan

### 1. Configuration Schema

```yaml
# config.yaml
logging:
  level: INFO  # Standard logging level
  developer_mode:
    enabled: false  # Disabled by default
    port: 4711
    db_path: .mcp_logs.sqlite3
    batch_size: 100  # Batch commits for performance
    batch_timeout: 1.0  # Seconds
    max_db_size_mb: 1000  # Rotate when exceeded
```

### 2. Database Schema

```sql
-- .mcp_logs.sqlite3
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    project_cwd TEXT NOT NULL,  -- Track which project generated the log
    trace_id TEXT,
    module TEXT,
    extra TEXT  -- JSON for additional context
);

CREATE INDEX idx_logs_timestamp ON logs(timestamp DESC);
CREATE INDEX idx_logs_instance ON logs(instance_id);
CREATE INDEX idx_logs_level ON logs(level);
CREATE INDEX idx_logs_project ON logs(project_cwd);
```

### 3. Core Implementation

#### ZMQ Log Server

```python
# mcp_second_brain/logging/server.py
import zmq
import sqlite3
import threading
import time
import json
from pathlib import Path
from typing import List, Dict, Any

class ZMQLogServer:
    def __init__(self, port: int, db_path: str, batch_size: int = 100, 
                 batch_timeout: float = 1.0):
        self.port = port
        self.db_path = db_path
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.shutdown_event = threading.Event()
        
        # ZMQ setup
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.bind(f"tcp://127.0.0.1:{port}")  # Local only
        self.socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout
        
        # Database setup
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()
        
    def _init_db(self):
        """Initialize database schema"""
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                project_cwd TEXT NOT NULL,
                trace_id TEXT,
                module TEXT,
                extra TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_logs_instance ON logs(instance_id);
            CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
            CREATE INDEX IF NOT EXISTS idx_logs_project ON logs(project_cwd);
        """)
        self.db.commit()
    
    def run(self):
        """Main server loop with batched writes"""
        batch: List[Dict[str, Any]] = []
        last_flush = time.time()
        
        while not self.shutdown_event.is_set():
            try:
                # Try to receive with timeout
                try:
                    msg = self.socket.recv_json(flags=zmq.NOBLOCK)
                    batch.append(msg)
                except zmq.Again:
                    # No message available
                    pass
                
                # Flush if batch is full or timeout reached
                now = time.time()
                if (len(batch) >= self.batch_size or 
                    (batch and now - last_flush >= self.batch_timeout)):
                    self._flush_batch(batch)
                    batch = []
                    last_flush = now
                    
            except Exception as e:
                # Log error but don't crash
                print(f"Log server error: {e}")
                continue
        
        # Final flush on shutdown
        if batch:
            self._flush_batch(batch)
        
        self.db.close()
        self.socket.close()
        self.context.term()
    
    def _flush_batch(self, batch: List[Dict[str, Any]]):
        """Write batch to database"""
        try:
            records = [
                (
                    msg.get('timestamp', time.time()),
                    msg.get('level', 'INFO'),
                    msg.get('message', ''),
                    msg.get('instance_id', 'unknown'),
                    msg.get('project_cwd', 'unknown'),
                    msg.get('trace_id'),
                    msg.get('module'),
                    json.dumps(msg.get('extra', {}))
                )
                for msg in batch
            ]
            
            self.db.executemany(
                """INSERT INTO logs 
                   (timestamp, level, message, instance_id, project_cwd, trace_id, module, extra)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                records
            )
            self.db.commit()
        except Exception as e:
            print(f"Failed to write batch: {e}")
    
    def shutdown(self):
        """Graceful shutdown"""
        self.shutdown_event.set()
```

#### ZMQ Log Handler

```python
# mcp_second_brain/logging/handler.py
import zmq
import json
import time
import logging
import threading
import queue
from typing import Optional

class ZMQLogHandler(logging.Handler):
    def __init__(self, address: str, instance_id: str):
        super().__init__()
        self.address = address
        self.instance_id = instance_id
        
        # Queue for async sending
        self.queue: queue.Queue = queue.Queue(maxsize=10000)
        self.sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self.sender_thread.start()
        
    def _sender_loop(self):
        """Background thread for sending logs"""
        context = zmq.Context()
        socket = context.socket(zmq.PUSH)
        socket.connect(self.address)
        socket.setsockopt(zmq.LINGER, 0)  # Don't block on close
        socket.setsockopt(zmq.SNDHWM, 1000)  # High water mark
        
        while True:
            try:
                record = self.queue.get(timeout=1.0)
                if record is None:  # Shutdown signal
                    break
                    
                msg = {
                    'timestamp': record.created,
                    'level': record.levelname,
                    'message': record.getMessage(),
                    'instance_id': self.instance_id,
                    'project_cwd': os.environ.get('MCP_PROJECT_PATH', os.getcwd()),  # Canonical project path
                    'module': record.name,
                    'trace_id': getattr(record, 'trace_id', None),
                    'extra': {
                        'pathname': record.pathname,
                        'lineno': record.lineno,
                        'funcName': record.funcName,
                    }
                }
                
                socket.send_json(msg, flags=zmq.NOBLOCK)
                
            except queue.Empty:
                continue
            except zmq.Again:
                # Socket buffer full, drop message
                pass
            except Exception as e:
                print(f"ZMQ handler error: {e}")
        
        socket.close()
        context.term()
    
    def emit(self, record: logging.LogRecord):
        """Queue log record for sending"""
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            # Drop message if queue is full
            pass
    
    def close(self):
        """Shutdown handler"""
        self.queue.put(None)  # Signal shutdown
        super().close()
```

#### Logging Setup

```python
# mcp_second_brain/logging/setup.py
import os
import logging
import threading
import uuid
import zmq
from typing import Optional

from .server import ZMQLogServer
from .handler import ZMQLogHandler
from ..config import get_settings

_log_server: Optional[ZMQLogServer] = None
_server_thread: Optional[threading.Thread] = None

def setup_logging():
    """Initialize logging system"""
    settings = get_settings()
    
    # Always setup basic logging
    logging.basicConfig(
        level=settings.logging.level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Developer mode logging
    if not settings.logging.developer_mode.enabled:
        return
    
    global _log_server, _server_thread
    
    port = settings.logging.developer_mode.port
    db_path = settings.logging.developer_mode.db_path
    
    # Try to start log server
    try:
        _log_server = ZMQLogServer(
            port=port,
            db_path=db_path,
            batch_size=settings.logging.developer_mode.batch_size,
            batch_timeout=settings.logging.developer_mode.batch_timeout
        )
        
        _server_thread = threading.Thread(target=_log_server.run)
        _server_thread.start()
        
        logging.info(f"Started ZMQ log server on port {port}")
        
    except zmq.ZMQError:
        # Port already in use, another instance is the server
        logging.info(f"ZMQ log server already running on port {port}")
    
    # Always setup client handler
    instance_id = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
    handler = ZMQLogHandler(f"tcp://localhost:{port}", instance_id)
    logging.getLogger().addHandler(handler)
    
    # Register shutdown hook
    import atexit
    atexit.register(shutdown_logging)

def shutdown_logging():
    """Graceful shutdown of logging system"""
    global _log_server, _server_thread
    
    if _log_server:
        _log_server.shutdown()
        _server_thread.join(timeout=5.0)
```

### 4. MCP Tool Implementation

```python
# mcp_second_brain/tools/logs.py
from typing import Optional, List, Dict, Any
import os
import sqlite3
import json
from datetime import datetime, timedelta

from ..config import get_settings
from .base import ToolSpec, tool
from .descriptors import Route

@tool(
    name="search_mcp_debug_logs",
    description="Search MCP server debug logs for troubleshooting (developer mode only)"
)
class SearchMCPDebugLogsToolSpec(ToolSpec):
    """Search through aggregated MCP server debug logs.
    
    By default, only shows logs from the current project directory.
    Use all_projects=True to search across all projects on this machine.
    """
    
    query: str = Route.prompt(
        description="Search query (SQL LIKE pattern)"
    )
    
    level: Optional[str] = Route.prompt(
        default=None,
        description="Filter by log level (DEBUG, INFO, WARNING, ERROR)"
    )
    
    since: Optional[str] = Route.prompt(
        default="1h",
        description="Time range (e.g., '1h', '30m', '1d')"
    )
    
    instance_id: Optional[str] = Route.prompt(
        default=None,
        description="Filter by specific instance ID"
    )
    
    all_projects: bool = Route.prompt(
        default=False,
        description="Search logs from all projects (default: current project only)"
    )
    
    limit: int = Route.prompt(
        default=100,
        description="Maximum results to return"
    )
    
    def _parse_since(self, since_str: str) -> float:
        """Parse time duration string to timestamp"""
        now = datetime.now()
        
        # Parse duration
        if since_str.endswith('m'):
            delta = timedelta(minutes=int(since_str[:-1]))
        elif since_str.endswith('h'):
            delta = timedelta(hours=int(since_str[:-1]))
        elif since_str.endswith('d'):
            delta = timedelta(days=int(since_str[:-1]))
        else:
            delta = timedelta(hours=1)  # Default 1 hour
        
        return (now - delta).timestamp()
    
    async def execute(self, **kwargs) -> str:
        settings = get_settings()
        db_path = settings.logging.developer_mode.db_path
        
        # Build SQL query
        conditions = ["timestamp > ?"]
        params = [self._parse_since(kwargs['since'])]
        
        # Filter by current project unless all_projects=True
        if not kwargs.get('all_projects', False):
            conditions.append("project_cwd = ?")
            params.append(os.environ.get('MCP_PROJECT_PATH', os.getcwd()))
        
        if kwargs.get('query'):
            conditions.append("message LIKE ?")
            params.append(f"%{kwargs['query']}%")
        
        if kwargs.get('level'):
            conditions.append("level = ?")
            params.append(kwargs['level'].upper())
        
        if kwargs.get('instance_id'):
            conditions.append("instance_id = ?")
            params.append(kwargs['instance_id'])
        
        where_clause = " AND ".join(conditions)
        
        # Query database
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute(
                f"""SELECT * FROM logs 
                    WHERE {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT ?""",
                params + [kwargs['limit']]
            )
            
            results = []
            for row in cursor:
                log_entry = dict(row)
                if log_entry.get('extra'):
                    log_entry['extra'] = json.loads(log_entry['extra'])
                results.append(log_entry)
            
            conn.close()
            
            # Format results
            if not results:
                return "No logs found matching criteria"
            
            output = []
            for log in results:
                timestamp = datetime.fromtimestamp(log['timestamp']).isoformat()
                # Show project path if searching across all projects
                project_info = f" [{log['project_cwd']}]" if kwargs.get('all_projects') else ""
                output.append(
                    f"[{timestamp}] {log['level']} ({log['instance_id']}){project_info} "
                    f"{log['module']}: {log['message']}"
                )
            
            return "\n".join(output)
            
        except Exception as e:
            return f"Error searching logs: {e}"

# Conditional registration
def register_log_tools():
    """Register logging tools if developer mode is enabled"""
    settings = get_settings()
    if settings.logging.developer_mode.enabled:
        return [SearchMCPDebugLogsToolSpec]
    return []
```

### 5. Testing Strategy

#### E2E Test Setup

```makefile
# Makefile additions
.PHONY: ensure-logging-server
ensure-logging-server:
	@echo "Ensuring logging server is running..."
	@claude -p 'test' 2>/dev/null || echo "Warning: Could not start logging server"

.PHONY: e2e
e2e: ensure-logging-server
	@echo "Running E2E tests with logging enabled..."
	@for scenario in $(SCENARIOS); do \
		echo "=== Running $$scenario tests ==="; \
		SHARED_TMP_VOLUME="e2e-tmp-$$scenario-test-$$(date +%s)"; \
		docker volume create $$SHARED_TMP_VOLUME; \
		docker run --rm \
			--name e2e-test-runner-$$scenario \
			-p 4711:4711 \
			-v $(PWD):/host-project:ro \
			-v /var/run/docker.sock:/var/run/docker.sock \
			-v $$SHARED_TMP_VOLUME:/tmp \
			-e CI_E2E=1 \
			-e MCP_PROJECT_PATH=$(PWD) \
			-e SHARED_TMP_VOLUME=$$SHARED_TMP_VOLUME \
			$(TEST_RUNNER_IMAGE) \
			pytest scenarios/test_$$scenario.py -v; \
		docker volume rm $$SHARED_TMP_VOLUME; \
	done
```

#### Docker Compose Updates

```yaml
# tests/e2e/docker-compose.yml
services:
  test-runner:
    image: ${TEST_RUNNER_IMAGE}
    container_name: e2e-test-runner
    ports:
      - "4711:4711"  # Forward logging port
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ${SHARED_TMP_VOLUME}:/tmp
      - ${HOST_PROJECT}:/host-project:ro
    environment:
      - CI_E2E=1
      - MCP_PROJECT_PATH=${MCP_PROJECT_PATH}
      - SHARED_TMP_VOLUME=${SHARED_TMP_VOLUME}

  mcp-server:
    image: mcp-e2e-server:latest
    network_mode: "service:test-runner"  # Share network namespace
    volumes:
      - ${SHARED_TMP_VOLUME}:/tmp
    environment:
      - CI_E2E=1
      - MCP_PROJECT_PATH=${MCP_PROJECT_PATH}
```

### 6. Integration Points

#### Server Startup

```python
# mcp_second_brain/server.py
from .logging.setup import setup_logging

def main():
    """Main entry point"""
    # Initialize logging first
    setup_logging()
    
    # Rest of server initialization
    # ...
```

#### Tool Registration

```python
# mcp_second_brain/tools/definitions.py
from .logs import register_log_tools

def get_all_tools():
    """Get all available tools"""
    tools = [
        # ... existing tools ...
    ]
    
    # Add logging tools if enabled
    tools.extend(register_log_tools())
    
    return tools
```

### 7. Operational Considerations

#### Database Maintenance

```python
# mcp_second_brain/logging/maintenance.py
import sqlite3
import os
from pathlib import Path

def rotate_logs(db_path: str, max_size_mb: int = 1000):
    """Rotate logs when database exceeds size limit"""
    db_size = Path(db_path).stat().st_size / (1024 * 1024)
    
    if db_size > max_size_mb:
        # Archive old database
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = f"{db_path}.{timestamp}"
        os.rename(db_path, archive_path)
        
        # Compress archive
        import gzip
        with open(archive_path, 'rb') as f_in:
            with gzip.open(f"{archive_path}.gz", 'wb') as f_out:
                f_out.writelines(f_in)
        os.remove(archive_path)

def cleanup_old_logs(db_path: str, days: int = 7):
    """Remove logs older than specified days"""
    conn = sqlite3.connect(db_path)
    cutoff = time.time() - (days * 24 * 60 * 60)
    
    conn.execute("DELETE FROM logs WHERE timestamp < ?", (cutoff,))
    conn.execute("VACUUM")  # Reclaim space
    conn.commit()
    conn.close()
```

## Migration Plan

1. **Phase 1**: Implement core logging system (ZMQ server, handler, setup)
2. **Phase 2**: Add MCP tool for log searching
3. **Phase 3**: Update E2E test infrastructure
4. **Phase 4**: Add maintenance utilities
5. **Phase 5**: Documentation and developer guide

## Success Criteria

1. **Performance**: < 0.1ms latency per log call
2. **Reliability**: No lost logs under normal operation
3. **Scalability**: Handle 10,000+ logs/second
4. **Storage**: Automatic rotation at 1GB
5. **Query Speed**: < 100ms for typical searches

## Future Enhancements

1. **Structured Logging**: Add support for OpenTelemetry-style spans and traces
2. **Remote Access**: Optional HTTP API for remote log access
3. **Alerting**: Real-time alerts for ERROR level logs
4. **Visualization**: Web UI for log analysis
5. **Export**: Support for exporting to standard formats (JSON, CSV)

## FAQ: Design Decisions

### Why not use OpenTelemetry or Cloud Logging?

- **No background daemons**: Must follow SQLite pattern - start/die with process
- **No cloud dependencies**: Not all users have GCP/AWS accounts
- **Zero configuration**: Must work out-of-the-box for developers

### Why ZeroMQ instead of simpler alternatives?

We evaluated several options:
- **Raw TCP**: Would require implementing reconnection, queueing, backpressure
- **Redis**: Requires separate service, adds operational complexity
- **HTTP**: Too slow (handshake per request), high overhead
- **nanomsg**: Still in beta, less mature than ZeroMQ

ZeroMQ provides high performance (5M+ msgs/sec), automatic reconnection, and built-in queueing with minimal code.

### Why not write directly to shared SQLite?

- **Lock contention**: Multiple writers to SQLite cause "database is locked" errors
- **Performance**: Even with WAL mode, concurrent writes serialize
- **Separation of concerns**: Logs are high-volume disposable data, shouldn't mix with session state
- **o3's recommendation**: Use separate database file for observability

### Why network-based instead of file-based?

User requirement: "hell no: docker exec test-runner cat /tmp/.mcp_logs/aggregated.jsonl. No need for sharing any files. Just an address and port."

Network communication works across Docker boundaries without complex volume mounting.

### Why require `claude -p 'test'` for E2E tests?

- **Persistent storage**: Logs must survive ephemeral containers
- **Native process requirement**: Logging server needs to run on host
- **Acceptable tradeoff**: Adds only few seconds to test startup
- **Future-proof**: Can adapt when Gemini CLI or other tools emerge

### Why developer_mode configuration?

- **Zero impact on production**: Regular users don't need logging infrastructure
- **No unnecessary dependencies**: ZeroMQ only installed for developers
- **Clean separation**: Production vs development clearly delineated
- **Explicit opt-in**: Prevents accidental exposure of debug tools

### Why the specific tool name `search_mcp_debug_logs`?

- **Clarity for LLMs**: Makes it obvious this is for debugging, not general use
- **Prevents accidental use**: Won't be confused with production logging tools
- **Self-documenting**: Name explains exactly what it does

### Why track project_cwd and filter by default?

- **Multi-project development**: Developers may have multiple Claude instances
- **Noise reduction**: Don't want logs from project A when debugging project B  
- **Intentional cross-project**: Must explicitly set `all_projects=True`
- **Docker compatibility**: Uses `MCP_PROJECT_PATH` env var for consistent paths

### Implementation lessons from reviews

From o3 and Gemini reviews:
- **Batch commits**: Never commit after each message (performance killer)
- **Graceful shutdown**: Use threading.Event, not daemon threads
- **Error resilience**: Wrap server loop in try/except, don't crash on bad messages
- **Security**: Bind to `127.0.0.1:4711`, not `*:4711`
- **No blocking**: Set `ZMQ_LINGER=0` to prevent hangs on shutdown
- **Fallback**: If logging fails, continue operating (log to stderr)

## Conclusion

This logging system provides a robust, high-performance solution for debugging MCP servers in complex Docker-in-Docker environments while maintaining zero impact on regular users. The architecture balances simplicity with power, providing developers with the tools they need without compromising the core MCP experience.
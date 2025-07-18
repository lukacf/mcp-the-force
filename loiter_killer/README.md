# Loiter Killer Service

A service that implements time-to-live (TTL) for OpenAI vector stores and files, preventing them from accumulating forever.

## Purpose

OpenAI vector stores and files have no built-in expiration - they persist indefinitely unless manually deleted. This creates several problems:
- **Hard limit of 100 vector stores** per account
- **Storage costs** for files that are no longer needed
- **Quota exhaustion** during development when servers restart frequently
- **Orphaned resources** when clients disconnect or crash

Loiter Killer solves this by:
- Implementing a 1-hour TTL for all vector stores and their associated files
- Tracking resources by session ID across server restarts
- Reusing existing vector stores within their TTL window
- Automatically cleaning up expired resources every 5 minutes
- Providing lease renewal for long-running operations

## Running

### Docker (Recommended)
```bash
docker-compose up loiter-killer
```

### Standalone
```bash
cd loiter_killer
python loiter_killer.py
```

## Architecture

See [../docs/loiter-killer-architecture.md](../docs/loiter-killer-architecture.md) for detailed documentation.

## Requirements

- Python 3.11+
- OpenAI API key (for vector store management)
- SQLite (for session tracking)

## How It Works

1. **Resource Tracking**: When MCP creates a vector store, it registers it with Loiter Killer along with the session ID
2. **TTL Management**: Each resource gets a 1-hour lease from last access
3. **Automatic Cleanup**: Every 5 minutes, expired resources are deleted from OpenAI
4. **Lease Renewal**: Long operations can extend the TTL to prevent premature deletion
5. **Crash Recovery**: If MCP restarts, it can reclaim existing resources within their TTL window

Without this service, OpenAI resources would accumulate forever, eventually hitting quota limits and requiring manual cleanup.

## API Endpoints

- `GET /health` - Health check
- `POST /session/{id}/acquire` - Get or create vector store for session
- `POST /session/{id}/files` - Track files in vector store  
- `POST /session/{id}/renew` - Extend TTL by 1 hour
- `POST /cleanup` - Trigger manual cleanup of expired resources
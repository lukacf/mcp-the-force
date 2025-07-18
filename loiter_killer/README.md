# Loiter Killer Service

A lightweight service that prevents OpenAI vector store limit errors by managing store lifecycle across ephemeral MCP server instances.

## Purpose

OpenAI has a limit of 100 vector stores per account. The MCP Second Brain server creates vector stores for large file attachments, but when the server restarts (which happens frequently during development), it loses track of these stores. This leads to "zombie" vector stores that count against the quota but are never cleaned up.

Loiter Killer solves this by:
- Tracking vector stores by session ID across server restarts
- Reusing existing vector stores for the same session
- Automatically cleaning up unused stores after 1 hour

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

## API Endpoints

- `GET /health` - Health check
- `POST /session/{id}/acquire` - Get or create vector store for session
- `POST /session/{id}/files` - Track files in vector store
- `POST /session/{id}/renew` - Extend lease by 1 hour
- `POST /cleanup` - Trigger manual cleanup
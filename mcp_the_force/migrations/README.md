# Database Migrations

This directory contains database migration scripts for MCP The Force.

## Migration System

The migration system provides:
- Automatic database backup before migrations
- Transaction-based execution (all-or-nothing)
- Rollback support on errors
- Idempotent migrations (safe to run multiple times)
- Schema versioning

## Running Migrations

### Check Current Status
```bash
python mcp_the_force/migrations/migrate.py status
```

### Run All Pending Migrations
```bash
python mcp_the_force/migrations/migrate.py migrate
```

### Dry Run (Preview Changes)
```bash
python mcp_the_force/migrations/migrate.py migrate --dry-run
```

### Migrate to Specific Version
```bash
python mcp_the_force/migrations/migrate.py migrate --target 1
```

### Rollback (Restore from Backup)
```bash
python mcp_the_force/migrations/migrate.py rollback --to-version 0
```

## Migration Files

Migration files follow the naming convention: `XXX_description.sql` where XXX is a zero-padded version number.

### Current Migrations

1. **001_unified_vector_stores.sql**
   - Unifies separate `vector_stores` and `stores` tables into a single schema
   - Adds support for multiple vector store providers
   - Improves index coverage and query performance
   - Adds rollover support for large vector stores

## Safety Features

1. **Automatic Backups**: Before any migration, a timestamped backup is created
2. **Transaction Safety**: All changes are wrapped in transactions
3. **Idempotency**: Migrations check if they've already been applied
4. **Rollback Scripts**: Each migration has a corresponding rollback script
5. **Version Tracking**: Schema version is tracked in the database

## Database Schema

After migration 001, the unified schema includes:

```sql
CREATE TABLE vector_stores (
    vector_store_id TEXT PRIMARY KEY,
    name TEXT UNIQUE,              -- For named stores (history system)
    session_id TEXT UNIQUE,        -- For session-specific stores
    provider TEXT NOT NULL,        -- Vector store provider
    provider_metadata TEXT,        -- Provider-specific JSON metadata
    is_protected INTEGER DEFAULT 0, -- Prevent accidental deletion
    is_active INTEGER DEFAULT 1,    -- Active/inactive status
    created_at INTEGER NOT NULL,    -- Unix timestamp
    expires_at INTEGER,            -- Unix timestamp (optional)
    updated_at INTEGER NOT NULL,    -- Unix timestamp
    document_count INTEGER DEFAULT 0,
    rollover_from TEXT,            -- Previous store ID for rollover chain
    
    -- Constraint: Either name OR session_id must be set, not both
    CHECK (
        (name IS NOT NULL AND session_id IS NULL) OR
        (name IS NULL AND session_id IS NOT NULL)
    )
);
```

## Development Guidelines

When creating new migrations:

1. Use the next available version number
2. Include both forward and rollback logic
3. Make migrations idempotent
4. Test on a copy of production data
5. Document significant schema changes
6. Consider performance impact of migrations on large databases
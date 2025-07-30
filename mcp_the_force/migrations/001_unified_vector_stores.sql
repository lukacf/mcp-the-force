-- Migration 001: Unified Vector Stores
-- This migration unifies the separate vector_stores and stores tables into a single unified schema

-- Start transaction
BEGIN TRANSACTION;

-- Create schema versioning table if it doesn't exist
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at INTEGER NOT NULL
);

-- Create new unified vector_stores table (with new name to avoid conflicts)
CREATE TABLE IF NOT EXISTS vector_stores_unified (
    vector_store_id TEXT PRIMARY KEY,
    name TEXT UNIQUE,
    session_id TEXT UNIQUE,
    provider TEXT NOT NULL CHECK(provider IN ('openai', 'inmemory', 'pinecone', 'hnsw')),
    provider_metadata TEXT,
    is_protected INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    expires_at INTEGER,
    updated_at INTEGER NOT NULL,
    document_count INTEGER DEFAULT 0,
    rollover_from TEXT REFERENCES vector_stores_unified(vector_store_id),
    
    CHECK (
        (name IS NOT NULL AND session_id IS NULL) OR
        (name IS NULL AND session_id IS NOT NULL)
    )
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_vs_session_id ON vector_stores_unified(session_id);
CREATE INDEX IF NOT EXISTS idx_vs_name ON vector_stores_unified(name);
CREATE INDEX IF NOT EXISTS idx_vs_expires_at ON vector_stores_unified(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_vs_active_named ON vector_stores_unified(name, is_active) WHERE name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_vs_rollover ON vector_stores_unified(rollover_from) WHERE rollover_from IS NOT NULL;

-- Migrate data from old vector_stores table (session stores)
INSERT OR IGNORE INTO vector_stores_unified (
    vector_store_id,
    session_id,
    provider,
    is_protected,
    created_at,
    expires_at,
    updated_at
)
SELECT 
    vector_store_id,
    session_id,
    provider,
    COALESCE(protected, 0),
    created_at,
    expires_at,
    updated_at
FROM vector_stores
WHERE EXISTS (SELECT 1 FROM sqlite_master WHERE type='table' AND name='vector_stores');

-- Drop old table and rename new one
DROP TABLE IF EXISTS vector_stores;
ALTER TABLE vector_stores_unified RENAME TO vector_stores;

-- Record migration
INSERT INTO schema_version (version, applied_at) VALUES (1, unixepoch());

COMMIT;
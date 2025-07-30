-- Rollback for Migration 001: Unified Vector Stores
-- This script reverts the unified vector_stores table back to separate tables

BEGIN TRANSACTION;

-- Verify we're at version 1 before rolling back
CREATE TEMP TABLE rollback_check AS
SELECT CASE 
    WHEN (SELECT MAX(version) FROM schema_version) = 1 THEN 1
    ELSE 0
END as can_rollback;

CREATE TRIGGER abort_if_wrong_version
BEFORE DELETE ON schema_version
WHEN (SELECT can_rollback FROM rollback_check) = 0
BEGIN
    SELECT RAISE(ABORT, 'Cannot rollback: database is not at version 1');
END;

-- Recreate original vector_stores table structure
CREATE TABLE vector_stores_original (
    session_id TEXT PRIMARY KEY,
    vector_store_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    protected INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

-- Recreate original stores table structure
CREATE TABLE stores_original (
    store_id TEXT PRIMARY KEY,
    store_type TEXT NOT NULL CHECK(store_type IN ('conversation','commit')),
    doc_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    is_active INTEGER NOT NULL CHECK(is_active IN (0,1))
);

-- Migrate session stores back
INSERT INTO vector_stores_original (
    session_id,
    vector_store_id,
    provider,
    expires_at,
    protected,
    created_at,
    updated_at
)
SELECT 
    session_id,
    vector_store_id,
    provider,
    COALESCE(expires_at, strftime('%s', 'now', '+365 days')),
    is_protected,
    created_at,
    updated_at
FROM vector_stores
WHERE session_id IS NOT NULL;

-- Migrate memory stores back
INSERT INTO stores_original (
    store_id,
    store_type,
    doc_count,
    created_at,
    is_active
)
SELECT 
    vector_store_id,
    CASE 
        WHEN name LIKE 'project-conversation%' THEN 'conversation'
        WHEN name LIKE 'project-commit%' THEN 'commit'
        ELSE 'conversation'  -- Default fallback
    END as store_type,
    document_count,
    datetime(created_at, 'unixepoch') as created_at,
    is_active
FROM vector_stores
WHERE name IS NOT NULL;

-- Drop the unified table
DROP TABLE vector_stores;

-- Rename tables back to original names
ALTER TABLE vector_stores_original RENAME TO vector_stores;
ALTER TABLE stores_original RENAME TO stores;

-- Recreate original indexes
CREATE INDEX idx_vector_stores_updated ON vector_stores(updated_at);
CREATE INDEX idx_vector_stores_expires ON vector_stores(expires_at);
CREATE UNIQUE INDEX idx_active_store ON stores (store_type) WHERE is_active = 1;

-- Remove migration record
DELETE FROM schema_version WHERE version = 1;

-- Clean up
DROP TRIGGER abort_if_wrong_version;
DROP TABLE rollback_check;

COMMIT;

-- Verify rollback success
SELECT 'Rollback completed successfully. Restored ' || 
    (SELECT COUNT(*) FROM vector_stores) || ' session stores and ' ||
    (SELECT COUNT(*) FROM stores) || ' memory stores.' as status;
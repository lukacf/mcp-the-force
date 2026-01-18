"""
RCT: Session Storage Round-Trip Tests

These tests validate that CLI session mappings and conversation history
with CLI metadata are correctly persisted and retrieved.

Gate 0 requirement: All tests must be green before Phase 1.
"""

import pytest
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

# Test the storage layer directly without importing the full application
# This ensures RCT tests can run early, before full implementation exists


@dataclass
class CLISessionMapping:
    """Represents a mapping from unified session to CLI-specific session.

    This is what we PLAN to store. RCT validates the storage layer can handle it.
    """

    project: str
    session_id: str  # Our unified session ID
    cli_name: str  # "claude", "gemini", "codex"
    cli_session_id: str  # The CLI's native session/thread ID
    created_at: int
    last_used_at: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class CLISessionBridgeDB:
    """Minimal SQLite storage for CLI session mappings.

    This is a simplified version of what we'll implement in Phase 2.
    RCT validates the schema and round-trip behavior.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        """Create the CLI session mapping table."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cli_session_mappings (
                project TEXT NOT NULL,
                session_id TEXT NOT NULL,
                cli_name TEXT NOT NULL,
                cli_session_id TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_used_at INTEGER NOT NULL,
                metadata TEXT,
                PRIMARY KEY (project, session_id, cli_name)
            )
        """)
        self._conn.commit()

    def store_mapping(self, mapping: CLISessionMapping) -> None:
        """Store a CLI session mapping."""
        import json

        metadata_json = json.dumps(mapping.metadata) if mapping.metadata else None

        self._conn.execute(
            """
            INSERT OR REPLACE INTO cli_session_mappings
            (project, session_id, cli_name, cli_session_id, created_at, last_used_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mapping.project,
                mapping.session_id,
                mapping.cli_name,
                mapping.cli_session_id,
                mapping.created_at,
                mapping.last_used_at,
                metadata_json,
            ),
        )
        self._conn.commit()

    def get_mapping(
        self, project: str, session_id: str, cli_name: str
    ) -> Optional[CLISessionMapping]:
        """Retrieve a CLI session mapping."""
        import json

        cursor = self._conn.execute(
            """
            SELECT cli_session_id, created_at, last_used_at, metadata
            FROM cli_session_mappings
            WHERE project = ? AND session_id = ? AND cli_name = ?
            """,
            (project, session_id, cli_name),
        )
        row = cursor.fetchone()

        if not row:
            return None

        cli_session_id, created_at, last_used_at, metadata_json = row
        metadata = json.loads(metadata_json) if metadata_json else {}

        return CLISessionMapping(
            project=project,
            session_id=session_id,
            cli_name=cli_name,
            cli_session_id=cli_session_id,
            created_at=created_at,
            last_used_at=last_used_at,
            metadata=metadata,
        )

    def close(self):
        """Close the database connection."""
        self._conn.close()


class TestCLISessionMappingRoundTrip:
    """RCT: Verify CLI session mapping storage round-trips correctly."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_cli_sessions.db"
        db = CLISessionBridgeDB(str(db_path))
        yield db
        db.close()

    def test_basic_mapping_roundtrip(self, db):
        """Write → Read → Equals for basic CLI session mapping."""
        now = int(time.time())

        original = CLISessionMapping(
            project="/test/project",
            session_id="test-session-001",
            cli_name="claude",
            cli_session_id="claude-abc-123-def",
            created_at=now,
            last_used_at=now,
            metadata={},
        )

        # Write
        db.store_mapping(original)

        # Read
        retrieved = db.get_mapping(
            project=original.project,
            session_id=original.session_id,
            cli_name=original.cli_name,
        )

        # Equals
        assert retrieved is not None
        assert retrieved.project == original.project
        assert retrieved.session_id == original.session_id
        assert retrieved.cli_name == original.cli_name
        assert retrieved.cli_session_id == original.cli_session_id
        assert retrieved.created_at == original.created_at
        assert retrieved.last_used_at == original.last_used_at
        assert retrieved.metadata == original.metadata

    def test_mapping_with_metadata_roundtrip(self, db):
        """Verify complex metadata survives round-trip."""
        now = int(time.time())

        original = CLISessionMapping(
            project="/test/project",
            session_id="test-session-002",
            cli_name="gemini",
            cli_session_id="gemini-session-xyz",
            created_at=now,
            last_used_at=now,
            metadata={
                "cli_version": "1.2.3",
                "model": "gemini-3-pro",
                "output_size_bytes": 1024,
                "return_code": 0,
                "raw_output_path": "/tmp/output.json",
                "nested": {"key": "value", "list": [1, 2, 3]},
            },
        )

        db.store_mapping(original)
        retrieved = db.get_mapping(
            original.project, original.session_id, original.cli_name
        )

        assert retrieved is not None
        assert retrieved.metadata == original.metadata
        assert retrieved.metadata["nested"]["list"] == [1, 2, 3]

    def test_multiple_clis_same_session(self, db):
        """Same session_id can map to different CLI sessions."""
        now = int(time.time())

        claude_mapping = CLISessionMapping(
            project="/test/project",
            session_id="shared-session-001",
            cli_name="claude",
            cli_session_id="claude-session-aaa",
            created_at=now,
            last_used_at=now,
        )

        gemini_mapping = CLISessionMapping(
            project="/test/project",
            session_id="shared-session-001",  # Same session_id
            cli_name="gemini",
            cli_session_id="gemini-session-bbb",
            created_at=now,
            last_used_at=now,
        )

        codex_mapping = CLISessionMapping(
            project="/test/project",
            session_id="shared-session-001",  # Same session_id
            cli_name="codex",
            cli_session_id="codex-thread-ccc",
            created_at=now,
            last_used_at=now,
        )

        # Store all three
        db.store_mapping(claude_mapping)
        db.store_mapping(gemini_mapping)
        db.store_mapping(codex_mapping)

        # Retrieve each and verify independence
        claude_retrieved = db.get_mapping(
            "/test/project", "shared-session-001", "claude"
        )
        gemini_retrieved = db.get_mapping(
            "/test/project", "shared-session-001", "gemini"
        )
        codex_retrieved = db.get_mapping("/test/project", "shared-session-001", "codex")

        assert claude_retrieved.cli_session_id == "claude-session-aaa"
        assert gemini_retrieved.cli_session_id == "gemini-session-bbb"
        assert codex_retrieved.cli_session_id == "codex-thread-ccc"

    def test_update_existing_mapping(self, db):
        """Updating a mapping replaces the old one."""
        now = int(time.time())

        original = CLISessionMapping(
            project="/test/project",
            session_id="update-test",
            cli_name="claude",
            cli_session_id="old-session-id",
            created_at=now,
            last_used_at=now,
            metadata={"version": 1},
        )

        db.store_mapping(original)

        # Update with new CLI session
        updated = CLISessionMapping(
            project="/test/project",
            session_id="update-test",
            cli_name="claude",
            cli_session_id="new-session-id",  # Changed
            created_at=now,
            last_used_at=now + 100,  # Changed
            metadata={"version": 2},  # Changed
        )

        db.store_mapping(updated)

        # Should get the updated version
        retrieved = db.get_mapping("/test/project", "update-test", "claude")
        assert retrieved.cli_session_id == "new-session-id"
        assert retrieved.last_used_at == now + 100
        assert retrieved.metadata["version"] == 2

    def test_nonexistent_mapping_returns_none(self, db):
        """Getting a nonexistent mapping returns None, not error."""
        result = db.get_mapping("/no/such/project", "no-such-session", "no-such-cli")
        assert result is None

    def test_null_vs_empty_metadata(self, db):
        """Distinguish between None/null metadata and empty dict."""
        now = int(time.time())

        # Empty metadata (explicit {})
        empty_meta = CLISessionMapping(
            project="/test/project",
            session_id="empty-meta",
            cli_name="claude",
            cli_session_id="session-1",
            created_at=now,
            last_used_at=now,
            metadata={},  # Explicit empty dict
        )

        db.store_mapping(empty_meta)
        retrieved = db.get_mapping("/test/project", "empty-meta", "claude")

        # Should get back an empty dict, not None
        assert retrieved.metadata == {}
        assert retrieved.metadata is not None

    def test_special_characters_in_ids(self, db):
        """Session IDs with special characters round-trip correctly."""
        now = int(time.time())

        mapping = CLISessionMapping(
            project="/Users/test/my project",  # Space in path
            session_id="session-with-special-chars_123",
            cli_name="claude",
            cli_session_id="uuid-like-550e8400-e29b-41d4-a716-446655440000",
            created_at=now,
            last_used_at=now,
            metadata={"notes": "Contains 'quotes' and \"double quotes\""},
        )

        db.store_mapping(mapping)
        retrieved = db.get_mapping(
            mapping.project, mapping.session_id, mapping.cli_name
        )

        assert retrieved.project == mapping.project
        assert retrieved.cli_session_id == mapping.cli_session_id
        assert "quotes" in retrieved.metadata["notes"]


class TestConversationTurnWithCLIMetadata:
    """RCT: Verify conversation turns with CLI-specific metadata round-trip."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a temporary database with conversation history table."""
        db_path = tmp_path / "test_conversations.db"
        conn = sqlite3.connect(str(db_path))

        # Use the existing UnifiedSession schema structure
        conn.execute("""
            CREATE TABLE IF NOT EXISTS unified_sessions(
                project TEXT NOT NULL,
                tool TEXT NOT NULL,
                session_id TEXT NOT NULL,
                history TEXT,
                provider_metadata TEXT,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (project, tool, session_id)
            )
        """)
        conn.commit()

        yield conn
        conn.close()

    def test_cli_turn_metadata_roundtrip(self, db):
        """Conversation turn with CLI metadata preserves all fields."""
        import json

        now = int(time.time())

        # A conversation turn that includes CLI-specific metadata
        history = [
            {
                "role": "user",
                "content": "Fix the bug in main.py",
                "metadata": {
                    "source": "cli_agent",
                    "cli_name": "claude",
                    "cli_session_id": "claude-123",
                },
            },
            {
                "role": "assistant",
                "content": "I've analyzed main.py and found the issue...",
                "metadata": {
                    "source": "cli_agent",
                    "cli_name": "claude",
                    "cli_session_id": "claude-123",
                    "execution_time_ms": 5432,
                    "return_code": 0,
                    "summarized": True,
                    "raw_output_tokens": 15000,
                },
            },
        ]

        provider_metadata = {
            "api_format": "cli_agent",
            "cli_name": "claude",
            "cli_session_id": "claude-123",
            "cli_version": "1.0.5",
        }

        # Write
        db.execute(
            """
            INSERT INTO unified_sessions
            (project, tool, session_id, history, provider_metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "/test/project",
                "work_with",
                "cli-test-session",
                json.dumps(history),
                json.dumps(provider_metadata),
                now,
            ),
        )
        db.commit()

        # Read
        cursor = db.execute(
            """
            SELECT history, provider_metadata, updated_at
            FROM unified_sessions
            WHERE project = ? AND tool = ? AND session_id = ?
            """,
            ("/test/project", "work_with", "cli-test-session"),
        )
        row = cursor.fetchone()

        assert row is not None
        retrieved_history = json.loads(row[0])
        retrieved_metadata = json.loads(row[1])

        # Verify history round-trip
        assert len(retrieved_history) == 2
        assert retrieved_history[0]["metadata"]["cli_name"] == "claude"
        assert retrieved_history[1]["metadata"]["execution_time_ms"] == 5432
        assert retrieved_history[1]["metadata"]["summarized"] is True

        # Verify provider metadata round-trip
        assert retrieved_metadata["api_format"] == "cli_agent"
        assert retrieved_metadata["cli_version"] == "1.0.5"

    def test_cross_cli_history_roundtrip(self, db):
        """History with turns from multiple CLIs round-trips correctly."""
        import json

        now = int(time.time())

        # A conversation that spans multiple CLI agents
        history = [
            {
                "role": "user",
                "content": "Plan the refactoring",
                "metadata": {"source": "user"},
            },
            {
                "role": "assistant",
                "content": "Here's my plan for refactoring...",
                "metadata": {
                    "source": "cli_agent",
                    "cli_name": "claude",
                    "cli_session_id": "claude-plan-001",
                },
            },
            {
                "role": "user",
                "content": "Now implement step 1",
                "metadata": {"source": "user"},
            },
            {
                "role": "assistant",
                "content": "I'll implement step 1...",
                "metadata": {
                    "source": "cli_agent",
                    "cli_name": "codex",  # Different CLI!
                    "cli_session_id": "codex-impl-002",
                },
            },
        ]

        db.execute(
            """
            INSERT INTO unified_sessions
            (project, tool, session_id, history, provider_metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "/test/project",
                "work_with",
                "cross-cli-session",
                json.dumps(history),
                json.dumps({}),
                now,
            ),
        )
        db.commit()

        # Read and verify
        cursor = db.execute(
            "SELECT history FROM unified_sessions WHERE session_id = ?",
            ("cross-cli-session",),
        )
        row = cursor.fetchone()
        retrieved_history = json.loads(row[0])

        # Verify each turn's CLI origin is preserved
        assert retrieved_history[1]["metadata"]["cli_name"] == "claude"
        assert retrieved_history[3]["metadata"]["cli_name"] == "codex"
        assert retrieved_history[1]["metadata"]["cli_session_id"] == "claude-plan-001"
        assert retrieved_history[3]["metadata"]["cli_session_id"] == "codex-impl-002"

    def test_large_raw_output_metadata(self, db):
        """Large raw output references in metadata survive round-trip."""
        import json

        now = int(time.time())

        # Simulate storing reference to large raw output
        history = [
            {
                "role": "assistant",
                "content": "Summary of the analysis...",
                "metadata": {
                    "source": "cli_agent",
                    "cli_name": "gemini",
                    "raw_output_tokens": 50000,
                    "raw_output_compressed": True,
                    "raw_output_path": "/tmp/gemini_raw_12345.json.gz",
                    "raw_output_sha256": "abc123def456...",
                },
            }
        ]

        db.execute(
            """
            INSERT INTO unified_sessions
            (project, tool, session_id, history, provider_metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "/test/project",
                "work_with",
                "large-output-session",
                json.dumps(history),
                json.dumps({}),
                now,
            ),
        )
        db.commit()

        cursor = db.execute(
            "SELECT history FROM unified_sessions WHERE session_id = ?",
            ("large-output-session",),
        )
        row = cursor.fetchone()
        retrieved_history = json.loads(row[0])

        meta = retrieved_history[0]["metadata"]
        assert meta["raw_output_tokens"] == 50000
        assert meta["raw_output_compressed"] is True
        assert meta["raw_output_path"].endswith(".json.gz")

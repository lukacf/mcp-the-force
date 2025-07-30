#!/usr/bin/env python3
"""
Database migration runner for MCP The Force.

This script manages database schema migrations, including:
- Automatic backup before migrations
- Transaction-based migration execution
- Rollback support on error
- Idempotent migrations
"""

import sqlite3
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import logging
import argparse


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Raised when a migration fails."""

    pass


class DatabaseMigrator:
    """Handles database migrations with backup and rollback support."""

    def __init__(self, db_path: Path, migrations_dir: Path):
        self.db_path = db_path
        self.migrations_dir = migrations_dir
        self.backup_path: Optional[Path] = None

    def _get_current_version(self, conn: sqlite3.Connection) -> int:
        """Get the current schema version from the database."""
        try:
            cursor = conn.execute("SELECT MAX(version) FROM schema_version")
            result = cursor.fetchone()
            return int(result[0]) if result[0] is not None else 0
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return 0

    def _get_available_migrations(self) -> List[Tuple[int, Path]]:
        """Get list of available migration files."""
        migrations = []

        for file in self.migrations_dir.glob("*.sql"):
            # Skip rollback files
            if "_rollback" in file.stem:
                continue
            # Extract version number from filename (e.g., 001_unified_vector_stores.sql)
            try:
                version = int(file.stem.split("_")[0])
                migrations.append((version, file))
            except (ValueError, IndexError):
                logger.warning(f"Skipping invalid migration filename: {file}")

        return sorted(migrations, key=lambda x: x[0])

    def _create_backup(self) -> Path:
        """Create a backup of the database before migration."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = (
            self.db_path.parent
            / f"{self.db_path.stem}_backup_{timestamp}{self.db_path.suffix}"
        )

        logger.info(f"Creating backup: {backup_path}")
        shutil.copy2(self.db_path, backup_path)

        # Also backup WAL and SHM files if they exist
        for suffix in ["-wal", "-shm"]:
            wal_file = Path(str(self.db_path) + suffix)
            if wal_file.exists():
                shutil.copy2(wal_file, Path(str(backup_path) + suffix))

        self.backup_path = backup_path
        return backup_path

    def _execute_migration(
        self, conn: sqlite3.Connection, migration_file: Path, version: int
    ):
        """Execute a single migration file."""
        logger.info(f"Executing migration {version}: {migration_file.name}")

        with open(migration_file, "r") as f:
            sql = f.read()

        try:
            # Execute the migration SQL
            conn.executescript(sql)
            conn.commit()
            logger.info(f"Migration {version} completed successfully")

        except sqlite3.Error as e:
            logger.error(f"Migration {version} failed: {e}")
            raise MigrationError(f"Failed to execute migration {version}: {e}")

    def _restore_backup(self):
        """Restore the database from backup after a failed migration."""
        if not self.backup_path or not self.backup_path.exists():
            logger.error("No backup available to restore")
            return

        logger.info(f"Restoring database from backup: {self.backup_path}")

        # Close any existing connections
        sqlite3.connect(self.db_path).close()

        # Restore main database file
        shutil.copy2(self.backup_path, self.db_path)

        # Restore WAL and SHM files if they exist
        for suffix in ["-wal", "-shm"]:
            backup_wal = Path(str(self.backup_path) + suffix)
            if backup_wal.exists():
                shutil.copy2(backup_wal, Path(str(self.db_path) + suffix))

        logger.info("Database restored successfully")

    def migrate(
        self, target_version: Optional[int] = None, dry_run: bool = False
    ) -> bool:
        """
        Run migrations up to the target version.

        Args:
            target_version: Target version to migrate to. If None, migrate to latest.
            dry_run: If True, only show what would be done without executing.

        Returns:
            True if migrations were successful, False otherwise.
        """
        if not self.db_path.exists():
            logger.error(f"Database not found: {self.db_path}")
            return False

        # Get available migrations
        migrations = self._get_available_migrations()
        if not migrations:
            logger.info("No migrations found")
            return True

        # Determine target version
        max_version = migrations[-1][0]
        if target_version is None:
            target_version = max_version
        elif target_version > max_version:
            logger.error(
                f"Target version {target_version} exceeds available migrations (max: {max_version})"
            )
            return False

        # Connect to database
        conn = sqlite3.connect(self.db_path)
        try:
            current_version = self._get_current_version(conn)
            logger.info(f"Current schema version: {current_version}")

            # Find migrations to apply
            pending_migrations = [
                (v, f) for v, f in migrations if current_version < v <= target_version
            ]

            if not pending_migrations:
                logger.info("Database is already up to date")
                return True

            logger.info(f"Found {len(pending_migrations)} pending migration(s)")

            if dry_run:
                logger.info("Dry run mode - showing migrations that would be applied:")
                for version, file in pending_migrations:
                    logger.info(f"  - Migration {version}: {file.name}")
                return True

            # Create backup before starting migrations
            self._create_backup()

            # Apply migrations
            for version, migration_file in pending_migrations:
                try:
                    self._execute_migration(conn, migration_file, version)
                except MigrationError as e:
                    logger.error(f"Migration failed: {e}")
                    conn.close()
                    self._restore_backup()
                    return False

            logger.info(f"Successfully migrated to version {target_version}")
            return True

        finally:
            conn.close()

    def rollback(self, to_version: int) -> bool:
        """
        Rollback to a specific version using rollback SQL if available,
        otherwise restore from backup.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            current_version = self._get_current_version(conn)

            if current_version <= to_version:
                logger.warning(
                    f"Current version {current_version} is already at or below target version {to_version}"
                )
                return True

            # Look for rollback SQL files
            rollback_migrations = []
            for version in range(current_version, to_version, -1):
                rollback_file = self.migrations_dir / f"{version:03d}_*_rollback.sql"
                matches = list(self.migrations_dir.glob(rollback_file.name))
                if matches:
                    rollback_migrations.append((version, matches[0]))

            if rollback_migrations:
                logger.info(f"Found {len(rollback_migrations)} rollback migration(s)")

                # Create backup before rollback
                self._create_backup()

                # Execute rollback migrations
                for version, rollback_file in rollback_migrations:
                    try:
                        logger.info(f"Executing rollback for version {version}")
                        self._execute_migration(conn, rollback_file, version)
                    except MigrationError as e:
                        logger.error(f"Rollback failed: {e}")
                        conn.close()
                        self._restore_backup()
                        return False

                logger.info(f"Successfully rolled back to version {to_version}")
                return True
            else:
                # Fallback to backup restoration
                logger.warning("No rollback migrations found - restoring from backup")
                conn.close()

                backups = sorted(
                    self.db_path.parent.glob(
                        f"{self.db_path.stem}_backup_*{self.db_path.suffix}"
                    )
                )
                if not backups:
                    logger.error("No backups found")
                    return False

                # Find the most recent backup
                self.backup_path = backups[-1]
                self._restore_backup()

                return True

        finally:
            if conn:
                conn.close()

    def status(self) -> Tuple[int, List[int]]:
        """
        Get migration status.

        Returns:
            Tuple of (current_version, available_versions)
        """
        conn = sqlite3.connect(self.db_path)
        try:
            current = self._get_current_version(conn)
            available = [v for v, _ in self._get_available_migrations()]
            return current, available
        finally:
            conn.close()


def main():
    """Main entry point for the migration script."""
    parser = argparse.ArgumentParser(
        description="Database migration tool for MCP The Force"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Path to the database file (default: .mcp_sessions.sqlite3)",
        default=Path(".mcp_sessions.sqlite3"),
    )
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        help="Path to migrations directory",
        default=Path(__file__).parent,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Run pending migrations")
    migrate_parser.add_argument(
        "--target", type=int, help="Target version to migrate to (default: latest)"
    )
    migrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing",
    )

    # Status command
    subparsers.add_parser("status", help="Show migration status")

    # Rollback command
    rollback_parser = subparsers.add_parser(
        "rollback", help="Rollback to a previous version"
    )
    rollback_parser.add_argument(
        "--to-version", type=int, required=True, help="Version to rollback to"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Initialize migrator
    migrator = DatabaseMigrator(args.db_path, args.migrations_dir)

    # Execute command
    if args.command == "migrate":
        success = migrator.migrate(target_version=args.target, dry_run=args.dry_run)
        return 0 if success else 1

    elif args.command == "status":
        current, available = migrator.status()
        print(f"Current version: {current}")
        print(f"Available migrations: {available}")

        pending = [v for v in available if v > current]
        if pending:
            print(f"Pending migrations: {pending}")
        else:
            print("Database is up to date")

        return 0

    elif args.command == "rollback":
        success = migrator.rollback(args.to_version)
        return 0 if success else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())

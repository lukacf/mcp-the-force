#!/usr/bin/env python3
"""
OpenAI Resource Cleanup Manager
Monitors and cleans up vector stores and files to stay under limits.
"""

import asyncio
import os
import sys
import time
import sqlite3
from datetime import datetime
from openai import AsyncOpenAI
from dotenv import load_dotenv
from typing import Tuple, Optional, List
from pathlib import Path

# ANSI color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


class OpenAICleanupManager:
    def __init__(self, db_path: Optional[str] = None):
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print(f"{RED}Error: OPENAI_API_KEY not set{RESET}")
            sys.exit(1)
        self.client = AsyncOpenAI(api_key=api_key)

        # SQLite database path for MCP memory stores
        if db_path:
            self.db_path = Path(db_path)
        else:
            # Default to the project-local database path
            self.db_path = Path(".mcp-the-force/sessions.sqlite3")
            if not self.db_path.exists():
                print(
                    f"{YELLOW}Warning: Default database not found at {self.db_path}. Specify with --db=path/to/db.sqlite3{RESET}"
                )
                self.db_path = None

    async def get_stats(self) -> Tuple[int, int]:
        """Get current counts of vector stores and files."""
        # Count vector stores
        vs_response = await self.client.vector_stores.list(limit=100)
        vs_count = len(vs_response.data)

        # Count files more accurately
        file_count = 0
        has_more = True
        last_id = None

        # Count up to 10k files for reasonable accuracy
        while has_more and file_count < 10000:
            if last_id:
                files_response = await self.client.files.list(
                    purpose="assistants", limit=100, after=last_id
                )
            else:
                files_response = await self.client.files.list(
                    purpose="assistants", limit=100
                )

            file_count += len(files_response.data)
            has_more = files_response.has_more

            if files_response.data:
                last_id = files_response.data[-1].id
            else:
                break

        # If we hit the limit, show it as 10k+
        if has_more:
            return vs_count, f"{file_count}+"

        return vs_count, file_count

    async def monitor_mode(self):
        """Continuously monitor resource usage."""
        print(f"{BOLD}OpenAI Resource Monitor{RESET}")
        print("=" * 70)
        print("Press Ctrl+C to stop monitoring\n")

        last_vs_count = None
        last_file_count = None

        while True:
            try:
                vs_count, file_count = await self.get_stats()

                # Color code based on usage
                vs_color = GREEN if vs_count < 80 else YELLOW if vs_count < 95 else RED
                file_color = (
                    GREEN
                    if (isinstance(file_count, int) and file_count < 5000)
                    else YELLOW
                    if (isinstance(file_count, int) and file_count < 10000)
                    else RED
                )

                # Show changes
                vs_change = ""
                file_change = ""
                if last_vs_count is not None:
                    diff = vs_count - last_vs_count
                    if diff > 0:
                        vs_change = f" {RED}↑{diff}{RESET}"
                    elif diff < 0:
                        vs_change = f" {GREEN}↓{abs(diff)}{RESET}"

                if (
                    last_file_count is not None
                    and isinstance(file_count, int)
                    and isinstance(last_file_count, int)
                ):
                    diff = file_count - last_file_count
                    if diff > 0:
                        file_change = f" {RED}↑{diff}{RESET}"
                    elif diff < 0:
                        file_change = f" {GREEN}↓{abs(diff)}{RESET}"

                timestamp = datetime.now().strftime("%H:%M:%S")

                # Clear line and print status
                print(
                    f"\r[{timestamp}] VS: {vs_color}{vs_count}/100{RESET}{vs_change} | "
                    f"Files: {file_color}{file_count}{RESET}{file_change}",
                    end="",
                    flush=True,
                )

                # Warnings on new line
                if vs_count >= 99:
                    print(
                        f"\n{RED}🚨 CRITICAL: At vector store limit - creation will hang!{RESET}",
                        end="",
                    )
                elif vs_count >= 95:
                    print(
                        f"\n{YELLOW}⚠️  WARNING: Approaching vector store limit!{RESET}",
                        end="",
                    )

                last_vs_count = vs_count
                last_file_count = file_count

                await asyncio.sleep(3)  # Check every 3 seconds

            except KeyboardInterrupt:
                print("\n\nMonitoring stopped.")
                break
            except Exception as e:
                print(f"\n{RED}Error: {e}{RESET}")
                await asyncio.sleep(5)

    async def cleanup_vector_stores(
        self, target_count: int = 50, update_sqlite: bool = True
    ):
        """Clean up vector stores to reach target count.

        Args:
            target_count: Target number of vector stores to keep
            update_sqlite: If True, also update SQLite database to mark deleted stores as inactive
        """
        print(f"{BOLD}Vector Store Cleanup{RESET}")
        print("=" * 50)

        if update_sqlite and self.db_path and self.db_path.exists():
            print(f"📂 SQLite database: {self.db_path}")
        elif update_sqlite:
            print(f"{YELLOW}⚠️  SQLite update requested but database not found{RESET}")

        # Get all vector stores
        print("📊 Fetching vector store list...")
        vs_response = await self.client.vector_stores.list(limit=100)
        vector_stores = vs_response.data
        current_count = len(vector_stores)

        print(f"Current count: {current_count}")
        print(f"Target count: {target_count}")

        if current_count <= target_count:
            print(f"{GREEN}✓ Already at or below target!{RESET}")
            return

        to_delete = current_count - target_count
        print(f"\nWill delete {to_delete} vector stores...")

        # Sort by created_at (oldest first)
        vector_stores.sort(key=lambda x: x.created_at)

        # Filter out permanent project history stores
        deletable_stores = []
        protected_stores = []
        for vs in vector_stores:
            # Skip permanent project memories (they have no expiry and
            # their names always start with "project-").
            # This includes both conversation and commit stores
            if vs.name and (
                vs.name.startswith("project-conversations-")
                or vs.name.startswith("project-commits-")
                or vs.name.startswith("project-")
            ):
                print(f"{BLUE}⚡ Skipping permanent store: {vs.name}{RESET}")
                protected_stores.append(vs)
                continue
            deletable_stores.append(vs)

        if protected_stores:
            print(f"\n{BLUE}Protected stores: {len(protected_stores)}{RESET}")

        # Check if we have enough deletable stores
        if len(deletable_stores) < to_delete:
            print(
                f"{YELLOW}⚠️  Only {len(deletable_stores)} deletable stores available (requested {to_delete}){RESET}"
            )
            to_delete = len(deletable_stores)

        deleted = 0
        failed = 0

        print("\nDeleting oldest vector stores (20 in parallel):")
        print("-" * 30)

        # Process in batches of 20 for parallel deletion
        batch_size = 20
        stores_to_delete = deletable_stores[:to_delete]
        all_deleted_ids = []  # Track all successfully deleted IDs

        for batch_start in range(0, len(stores_to_delete), batch_size):
            batch_end = min(batch_start + batch_size, len(stores_to_delete))
            batch = stores_to_delete[batch_start:batch_end]

            # Create deletion tasks for this batch
            delete_tasks = []
            for vs in batch:
                delete_tasks.append(self._delete_vector_store(vs.id))

            # Run batch deletions in parallel
            print(
                f"\nProcessing batch {batch_start // batch_size + 1} ({len(batch)} stores)..."
            )
            results = await asyncio.gather(*delete_tasks, return_exceptions=True)

            # Count results and collect successfully deleted IDs
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed += 1
                    print(
                        f"{RED}✗ Failed to delete {batch[i].id[:16]}: {result}{RESET}"
                    )
                else:
                    deleted += 1
                    all_deleted_ids.append(batch[i].id)
                    print(f"{GREEN}✓ Deleted {batch[i].id[:16]}{RESET}")

            # Progress update
            total_processed = batch_end
            progress = total_processed / to_delete * 100
            print(f"\nProgress: {progress:3.0f}% ({total_processed}/{to_delete})")

            # Brief pause between batches for rate limiting
            if batch_end < len(stores_to_delete):
                await asyncio.sleep(0.5)

        print(f"\n\n{GREEN}✓ Cleanup complete!{RESET}")
        print(f"Deleted: {deleted}")
        print(f"Failed: {failed}")

        # Update SQLite database if requested
        if update_sqlite and all_deleted_ids and self.db_path and self.db_path.exists():
            updated_count = self._update_sqlite_stores(all_deleted_ids)
            if updated_count > 0:
                print(
                    f"{GREEN}✓ Updated {updated_count} stores in SQLite database{RESET}"
                )
            else:
                print(
                    f"{YELLOW}⚠️  No stores updated in SQLite (may already be inactive){RESET}"
                )

        # Show new count
        new_response = await self.client.vector_stores.list(limit=100)
        print(f"New count: {len(new_response.data)}")

    async def _delete_vector_store(self, vs_id: str):
        """Delete a single vector store."""
        try:
            await self.client.vector_stores.delete(vs_id)
            return True
        except Exception as e:
            raise e

    async def cleanup_files(self, max_files: int = 1000, batch_size: int = 100):
        """Clean up files by deleting until we reach target count."""
        print(f"{BOLD}File Cleanup (Stream Mode: {batch_size} concurrent){RESET}")
        print("=" * 50)

        # Quick initial count
        print("📊 Getting initial file count...")
        response = await self.client.files.list(purpose="assistants", limit=1)
        if not response.has_more and len(response.data) <= max_files:
            print(f"{GREEN}✓ File count already at or below {max_files}!{RESET}")
            return

        print(f"Target: Keep {max_files} files")
        print(f"Deleting files in batches of {batch_size}...\n")

        deleted = 0
        failed = 0
        start_time = time.time()
        last_id = None
        batch_num = 0

        # Keep deleting until we don't need to anymore
        while True:
            # Fetch next batch
            try:
                if last_id:
                    response = await self.client.files.list(
                        purpose="assistants", limit=batch_size, after=last_id
                    )
                else:
                    response = await self.client.files.list(
                        purpose="assistants", limit=batch_size
                    )
            except Exception as e:
                # Handle case where last_id was deleted by another process
                if "No such File object" in str(e):
                    print(
                        f"\n{YELLOW}Pagination cursor lost (file deleted). Restarting from beginning...{RESET}"
                    )
                    last_id = None
                    continue
                else:
                    raise

            if not response.data:
                break

            batch = response.data
            last_id = batch[-1].id if batch else None

            # Quick count to see if we should stop
            if deleted > 0 and deleted % 500 == 0:
                count_response = await self.client.files.list(
                    purpose="assistants", limit=1
                )
                if not count_response.has_more or (
                    len(count_response.data) == 1 and deleted >= 1
                ):
                    remaining_estimate = max_files  # Close enough
                    if remaining_estimate <= max_files:
                        print(f"\n{GREEN}✓ Reached target!{RESET}")
                        break

            # Delete this batch in parallel
            batch_num += 1
            delete_tasks = [self._delete_file(f.id) for f in batch]
            results = await asyncio.gather(*delete_tasks, return_exceptions=True)

            # Count results
            batch_deleted = sum(1 for r in results if not isinstance(r, Exception))
            batch_failed = len(results) - batch_deleted
            deleted += batch_deleted
            failed += batch_failed

            # Progress update
            elapsed = time.time() - start_time
            rate = deleted / elapsed if elapsed > 0 else 0

            print(
                f"\rBatch {batch_num} | Deleted: {deleted} | Failed: {failed} | "
                f"Rate: {rate:.0f} files/sec | Elapsed: {int(elapsed)}s",
                end="",
                flush=True,
            )

            # Stop if we've deleted enough (rough estimate)
            if max_files == 0:
                # Delete everything - keep going until no more files
                if not response.has_more:
                    break
            else:
                # Rough estimate - if we've deleted a lot, check actual count
                if deleted > 10000:
                    # Do actual count check
                    actual_count = 0
                    check_response = await self.client.files.list(
                        purpose="assistants", limit=100
                    )
                    actual_count = len(check_response.data)
                    if check_response.has_more:
                        actual_count = "many"

                    if isinstance(actual_count, int) and actual_count <= max_files:
                        print(
                            f"\n{GREEN}✓ Reached target count: {actual_count} files remaining{RESET}"
                        )
                        break

        # Final stats
        elapsed = time.time() - start_time
        print(f"\n\n{GREEN}✓ File cleanup complete in {elapsed:.1f} seconds!{RESET}")
        print(f"Deleted: {deleted}")
        print(f"Failed: {failed}")
        print(f"Rate: {deleted / elapsed:.0f} files/sec")

    async def _delete_file(self, file_id: str):
        """Delete a single file."""
        try:
            await self.client.files.delete(file_id)
            return True
        except Exception as e:
            raise e

    def _update_sqlite_stores(self, deleted_ids: List[str]) -> int:
        """Update SQLite database to mark deleted stores as inactive.

        Args:
            deleted_ids: List of vector store IDs that were deleted

        Returns:
            Number of rows updated
        """
        if not self.db_path or not self.db_path.exists():
            return 0

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Update stores to mark as inactive
            placeholders = ",".join("?" for _ in deleted_ids)
            query = (
                f"UPDATE stores SET is_active = 0 WHERE store_id IN ({placeholders})"
            )

            cursor.execute(query, deleted_ids)
            updated = cursor.rowcount

            conn.commit()
            conn.close()

            return updated
        except Exception as e:
            print(f"{RED}Error updating SQLite: {e}{RESET}")
            return 0

    async def interactive_menu(self):
        """Interactive cleanup menu."""
        while True:
            print(f"\n{BOLD}OpenAI Resource Cleanup Manager{RESET}")
            print("=" * 50)

            # Get current stats
            vs_count, file_count = await self.get_stats()
            vs_color = GREEN if vs_count < 80 else YELLOW if vs_count < 95 else RED

            print("Current Status:")
            print(f"  Vector Stores: {vs_color}{vs_count}/100{RESET}")
            print(f"  Files: {file_count}")

            print("\nOptions:")
            print("1. Monitor resources (real-time)")
            print("2. Clean up vector stores")
            print("3. Clean up files")
            print("4. Emergency cleanup (delete 50% of vector stores)")
            print("5. Refresh stats")
            print("0. Exit")

            choice = input("\nSelect option: ")

            if choice == "1":
                await self.monitor_mode()
            elif choice == "2":
                target = input("Target vector store count (default 50): ")
                target = int(target) if target else 50
                update_sql = input("Update SQLite database? (yes/no, default yes): ")
                update_sql = update_sql.lower() != "no"
                await self.cleanup_vector_stores(target, update_sqlite=update_sql)
            elif choice == "3":
                max_files = input("Maximum files to keep (default 1000): ")
                max_files = int(max_files) if max_files else 1000
                await self.cleanup_files(max_files)
            elif choice == "4":
                print(
                    f"{YELLOW}⚠️  Emergency cleanup will delete 50% of vector stores!{RESET}"
                )
                confirm = input("Are you sure? (yes/no): ")
                if confirm.lower() == "yes":
                    await self.cleanup_vector_stores(50, update_sqlite=True)
            elif choice == "5":
                continue
            elif choice == "0":
                print("Goodbye!")
                break
            else:
                print(f"{RED}Invalid option{RESET}")


async def main():
    # Check for database path argument
    db_path = None
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--db=")]
    for arg in sys.argv[1:]:
        if arg.startswith("--db="):
            db_path = arg[5:]
            break

    manager = OpenAICleanupManager(db_path=db_path)

    # Parse command line arguments
    if len(args) > 0:
        if args[0] == "monitor":
            await manager.monitor_mode()
        elif args[0] == "cleanup-vs":
            target = int(args[1]) if len(args) > 1 else 50
            await manager.cleanup_vector_stores(target, update_sqlite=True)
        elif args[0] == "cleanup-files":
            max_files = int(args[1]) if len(args) > 1 else 1000
            batch_size = int(args[2]) if len(args) > 2 else 100
            await manager.cleanup_files(max_files, batch_size)
        else:
            print("Usage:")
            print(
                "  python openai_cleanup_manager.py [--db=path]          # Interactive mode"
            )
            print(
                "  python openai_cleanup_manager.py [--db=path] monitor  # Monitor mode"
            )
            print(
                "  python openai_cleanup_manager.py [--db=path] cleanup-vs [target]  # Cleanup vector stores"
            )
            print(
                "  python openai_cleanup_manager.py [--db=path] cleanup-files [max] [batch_size]  # Cleanup files"
            )
            print("\nOptions:")
            print(
                "  --db=path  Path to SQLite database (default: .mcp-the-force/sessions.sqlite3)"
            )
            print("\nExamples:")
            print(
                "  python openai_cleanup_manager.py cleanup-files 100  # Keep 100 files, 100 parallel"
            )
            print(
                "  python openai_cleanup_manager.py cleanup-files 0 200  # Delete ALL files, 200 parallel"
            )
    else:
        await manager.interactive_menu()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nCleanup manager stopped.")

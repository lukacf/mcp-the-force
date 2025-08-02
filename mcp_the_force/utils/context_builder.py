"""Context building with stable inline list support."""

import os
import logging
from typing import List, Tuple, Optional

from ..utils.fs import gather_file_paths_async
from ..utils.context_loader import load_specific_files_async
from ..utils.token_counter import count_tokens
from .stable_list_cache import StableListCache
from .file_tree import build_file_tree_from_paths

logger = logging.getLogger(__name__)


def estimate_tokens_from_size(size_bytes: int) -> int:
    """Fast estimate token count from file size (fallback only).

    Uses a heuristic of 3.5 bytes per token for initial rough estimates.
    This is only used when we can't read the file content.

    Args:
        size_bytes: File size in bytes

    Returns:
        Estimated token count
    """
    return max(1, int(size_bytes / 3.5))


def count_tokens_from_file(file_path: str) -> int:
    """Count actual tokens in a file using tiktoken.

    Reads the file content and uses tiktoken for accurate token counting.
    Falls back to size estimation if file cannot be read.

    Args:
        file_path: Path to file to count tokens for

    Returns:
        Actual token count
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return count_tokens([content])
    except (OSError, IOError, UnicodeDecodeError) as e:
        logger.warning(f"Could not read file {file_path} for token counting: {e}")
        # Fallback to size estimation
        try:
            size = os.path.getsize(file_path)
            return estimate_tokens_from_size(size)
        except (OSError, IOError):
            return 1


def sort_files_for_stable_list(file_paths: List[str]) -> List[str]:
    """Sort files to maximize useful inline content.

    Files are sorted by actual token count (ascending) then path.
    This puts more small files inline, maximizing the number
    of complete files available to the model.

    Uses tiktoken for accurate token counting, which adds 100-300ms
    but provides precise context management.

    Args:
        file_paths: List of file paths to sort

    Returns:
        Sorted list of file paths
    """
    file_info = []

    for path in file_paths:
        try:
            tokens = count_tokens_from_file(path)
            file_info.append((path, tokens))
        except Exception as e:
            logger.warning(f"Skipping file {path}: {e}")
            continue

    # Sort by token count (ascending) then path
    # This puts smaller files first
    file_info.sort(key=lambda x: (x[1], x[0]))

    return [path for path, _ in file_info]


async def build_context_with_stable_list(
    context_paths: List[str],
    session_id: str,
    cache: StableListCache,
    token_budget: int,
    priority_context: Optional[List[str]] = None,
) -> Tuple[List[Tuple[str, str, int]], List[str], str]:
    """Build context using stable-inline list approach.

    On first call with overflow, establishes a stable list of files
    that go inline. On subsequent calls, only sends changed files.

    Args:
        context_paths: List of paths to include in context
        session_id: Session identifier
        cache: StableListCache instance
        token_budget: Maximum tokens for inline content
        priority_context: Optional list of paths to prioritize for inline inclusion

    Returns:
        Tuple of (files_to_send_inline, files_for_vector_store, file_tree)
        - files_to_send_inline: List of (path, content, tokens) tuples
        - files_for_vector_store: List of file paths
        - file_tree: ASCII tree representation with INLINE markers
    """
    # Debug logging to understand file access issues
    logger.debug(f"DEBUG: CWD inside context_builder: {os.getcwd()}")
    logger.debug(f"DEBUG: Received context_paths: {context_paths}")

    # Check existence of each path
    for p in context_paths:
        abs_p = os.path.abspath(p)
        exists = os.path.exists(abs_p)
        logger.debug(
            f"DEBUG: Checking path '{p}' | abspath: '{abs_p}' | Exists? {exists}"
        )
        if exists:
            try:
                stat = os.stat(abs_p)
                logger.debug(
                    f"DEBUG: File stats - size: {stat.st_size}, mtime: {stat.st_mtime}"
                )
            except Exception as e:
                logger.debug(f"DEBUG: Error statting file: {e}")

    # Gather priority files first if provided
    priority_files = []
    if priority_context:
        priority_files = await gather_file_paths_async(priority_context)
        logger.info(f"Gathered {len(priority_files)} priority files")

    # Gather all files from context paths
    all_files = await gather_file_paths_async(context_paths)
    logger.info(f"Gathered {len(all_files)} files from context paths")

    # Check if we have a stable list
    stable_list = await cache.get_stable_list(session_id)

    if not stable_list:
        # First call or expired - establish the stable list
        logger.info(f"No stable list for session {session_id}, creating one")

        # Sort files deterministically
        sorted_regular_files = sort_files_for_stable_list(all_files)
        sorted_priority_files = (
            sort_files_for_stable_list(priority_files) if priority_files else []
        )

        # Combine with priority files first
        sorted_files = sorted_priority_files + [
            f for f in sorted_regular_files if f not in priority_files
        ]

        # Use actual token counting to determine split (accurate but slower)
        inline_paths = []
        overflow_paths = []
        remaining_budget = token_budget

        # Single pass: decide which files to inline using actual token counting
        # This is slower but eliminates the estimation errors that caused context overflow
        logger.debug(
            f"Using tiktoken for accurate token counting of {len(sorted_files)} files"
        )
        for file_path in sorted_files:
            try:
                actual_tokens = count_tokens_from_file(file_path)

                # Priority files ALWAYS go inline, regardless of budget
                if file_path in priority_files:
                    inline_paths.append(file_path)
                    remaining_budget -= actual_tokens  # Still track budget impact
                elif actual_tokens <= remaining_budget:
                    inline_paths.append(file_path)
                    remaining_budget -= actual_tokens
                else:
                    overflow_paths.append(file_path)
            except Exception as e:
                logger.warning(f"Error counting tokens for {file_path}: {e}")
                # If we can't count tokens, put it in overflow unless it's priority
                if file_path in priority_files:
                    # Priority files still go inline even if we can't count tokens
                    inline_paths.append(file_path)
                else:
                    overflow_paths.append(file_path)

        # Load file contents for inline files (we already have accurate token counts)
        logger.debug(
            f"Loading {len(inline_paths)} inline files (tiktoken-validated), {len(overflow_paths)} overflow files"
        )
        file_data = await load_specific_files_async(inline_paths)

        # No safety check needed - we used accurate tiktoken counts for selection
        # The file_data should exactly match our token budget calculations

        # Diagnostic logging: Show what old estimation would have given vs tiktoken
        if file_data:
            total_tiktoken = sum(tokens for _, _, tokens in file_data)
            total_size_estimate = sum(
                estimate_tokens_from_size(os.path.getsize(path))
                for path, _, _ in file_data
                if os.path.exists(path)
            )
            old_vs_new_ratio = (
                total_size_estimate / total_tiktoken if total_tiktoken > 0 else 0
            )
            logger.debug(
                f"[TIKTOKEN_ACCURACY] Files: {len(file_data)}, Tiktoken: {total_tiktoken:,}, "
                f"Size estimate: {total_size_estimate:,}, Old/New ratio: {old_vs_new_ratio:.2f}"
            )

        # Always save the stable list to establish a baseline for subsequent calls
        await cache.save_stable_list(session_id, inline_paths)
        logger.info(
            f"Saved stable list with {len(inline_paths)} inline files for session {session_id}"
        )

        # On first call, send all inline files
        files_to_send = file_data

        # Batch update the mtime/size info for all sent files for future change detection
        files_to_update = []
        for file_path, _, _ in files_to_send:
            try:
                stat = os.stat(file_path)
                files_to_update.append(
                    (file_path, int(stat.st_size), int(stat.st_mtime_ns))
                )
            except OSError as e:
                logger.warning(f"Could not stat file {file_path} for cache update: {e}")

        if files_to_update:
            await cache.batch_update_sent_files(session_id, files_to_update)
    else:
        # Subsequent call - only send changed files
        logger.info(f"Using existing stable list for session {session_id}")

        files_to_send = []
        overflow_paths = []

        # Combine all files (priority + regular)
        all_combined_files = list(set(priority_files + all_files))

        # Check each file in context
        for file_path in all_combined_files:
            # Priority files ALWAYS go inline, even if not in stable list
            if file_path in priority_files or file_path in stable_list:
                # This file should go inline
                if await cache.file_changed_since_last_send(session_id, file_path):
                    # File has changed, need to resend it
                    file_data = await load_specific_files_async([file_path])
                    if file_data:
                        files_to_send.append(file_data[0])
                        # Update sent info
                        try:
                            stat = os.stat(file_path)
                            await cache.update_sent_file_info(
                                session_id,
                                file_path,
                                int(stat.st_size),
                                int(stat.st_mtime_ns),
                            )
                        except OSError:
                            pass
                # else: file hasn't changed, skip it
            else:
                # This file wasn't in the stable list originally
                # Only add to overflow if it's a new file that wasn't tracked before
                if await cache.file_changed_since_last_send(session_id, file_path):
                    # New file that wasn't in the original stable list
                    overflow_paths.append(file_path)
                # else: file exists but hasn't changed, skip it entirely

        logger.info(f"Sending {len(files_to_send)} changed files inline")

    # Generate file tree from ALL files (context + priority)
    # Combine all files that were requested (deduplicated)
    all_requested_files = list(set(priority_files + all_files))  # All unique files
    if overflow_paths:
        # Only add overflow files that aren't already in all_files
        all_files_set = set(all_files)
        unique_overflow = [f for f in overflow_paths if f not in all_files_set]
        all_requested_files.extend(unique_overflow)

    # Determine which files are inline
    inline_file_paths = []
    if stable_list:
        # Use the stable list + priority files (priority always inline)
        inline_file_paths = list(set(stable_list) | set(priority_files))
    else:
        # Use the current inline paths
        inline_file_paths = list(inline_paths)

    # Build file tree showing only requested files with attached markers
    # We mark attachment files (not inline files) since inline is the majority
    attachment_paths = list(set(all_requested_files) - set(inline_file_paths))

    file_tree = build_file_tree_from_paths(
        all_paths=all_requested_files,
        attachment_paths=attachment_paths,  # Mark these as attached
        root_path=None,  # Will find common root automatically
    )

    logger.info(
        f"[CONTEXT_BUILDER] Completed: returning {len(files_to_send)} inline files, {len(overflow_paths)} overflow files, file tree with {len(attachment_paths)} attached markers"
    )
    return files_to_send, overflow_paths, file_tree

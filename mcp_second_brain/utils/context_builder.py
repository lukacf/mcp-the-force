"""Context building with stable inline list support."""

import os
import logging
from typing import List, Tuple, Optional

from ..utils.fs import gather_file_paths
from ..utils.context_loader import load_specific_files
from .stable_list_cache import StableListCache

logger = logging.getLogger(__name__)


def estimate_tokens(size_bytes: int) -> int:
    """Estimate token count from file size.

    Uses a conservative heuristic of 2 bytes per token to account for
    dense coding languages like JavaScript/TypeScript/Python.

    Args:
        size_bytes: File size in bytes

    Returns:
        Estimated token count
    """
    # Conservative estimate: ~2 bytes per token (better for code files)
    return max(1, size_bytes // 2)


def sort_files_for_stable_list(file_paths: List[str]) -> List[str]:
    """Sort files to maximize useful inline content.

    Files are sorted by token count (ascending) then path.
    This puts more small files inline, maximizing the number
    of complete files available to the model.

    Args:
        file_paths: List of file paths to sort

    Returns:
        Sorted list of file paths
    """
    file_info = []

    for path in file_paths:
        try:
            size = os.path.getsize(path)
            tokens = estimate_tokens(size)
            file_info.append((path, size, tokens))
        except (OSError, IOError) as e:
            logger.warning(f"Skipping file {path}: {e}")
            continue

    # Sort by token count (ascending) then path
    # This puts smaller files first
    file_info.sort(key=lambda x: (x[2], x[0]))

    return [path for path, _, _ in file_info]


async def build_context_with_stable_list(
    context_paths: List[str],
    session_id: str,
    cache: StableListCache,
    token_budget: int,
    attachments: Optional[List[str]] = None,
) -> Tuple[List[Tuple[str, str, int]], List[str]]:
    """Build context using stable-inline list approach.

    On first call with overflow, establishes a stable list of files
    that go inline. On subsequent calls, only sends changed files.

    Args:
        context_paths: List of paths to include in context
        session_id: Session identifier
        cache: StableListCache instance
        token_budget: Maximum tokens for inline content
        attachments: Optional list of attachment paths

    Returns:
        Tuple of (files_to_send_inline, files_for_vector_store)
        - files_to_send_inline: List of (path, content, tokens) tuples
        - files_for_vector_store: List of file paths
    """
    # Debug logging to understand file access issues
    logger.info(f"DEBUG: CWD inside context_builder: {os.getcwd()}")
    logger.info(f"DEBUG: Received context_paths: {context_paths}")

    # Check existence of each path
    for p in context_paths:
        abs_p = os.path.abspath(p)
        exists = os.path.exists(abs_p)
        logger.info(
            f"DEBUG: Checking path '{p}' | abspath: '{abs_p}' | Exists? {exists}"
        )
        if exists:
            try:
                stat = os.stat(abs_p)
                logger.info(
                    f"DEBUG: File stats - size: {stat.st_size}, mtime: {stat.st_mtime}"
                )
            except Exception as e:
                logger.info(f"DEBUG: Error statting file: {e}")

    # Gather all files from context paths
    all_files = gather_file_paths(context_paths)
    logger.info(f"Gathered {len(all_files)} files from context paths")

    # Check if we have a stable list
    stable_list = await cache.get_stable_list(session_id)

    if not stable_list:
        # First call or expired - establish the stable list
        logger.info(f"No stable list for session {session_id}, creating one")

        # Sort files deterministically
        sorted_files = sort_files_for_stable_list(all_files)

        # Use size-based estimation to determine split (fast)
        inline_paths = []
        overflow_paths = []
        remaining_budget = token_budget

        # First pass: decide which files to inline using fast size estimation
        for file_path in sorted_files:
            try:
                size = os.path.getsize(file_path)
                est_tokens = estimate_tokens(size)
                if est_tokens <= remaining_budget:
                    inline_paths.append(file_path)
                    remaining_budget -= est_tokens
                else:
                    overflow_paths.append(file_path)
            except (OSError, IOError):
                # If we can't stat the file, put it in overflow
                overflow_paths.append(file_path)

        # Second pass: load and tokenize only files that will be sent inline
        logger.info(
            f"Loading {len(inline_paths)} inline files (estimated), {len(overflow_paths)} overflow files"
        )
        file_data = load_specific_files(inline_paths)

        # Safety check: trim if our size estimates were too optimistic
        file_data.sort(key=lambda t: t[2])  # Sort by actual token count
        used_tokens = 0
        trimmed_data = []
        for file_path, content, tokens in file_data:
            if used_tokens + tokens <= token_budget:
                trimmed_data.append((file_path, content, tokens))
                used_tokens += tokens
            else:
                # Move over-budget files to overflow
                overflow_paths.append(file_path)
                inline_paths.remove(file_path)

        file_data = trimmed_data

        # Check if we actually have overflow
        if overflow_paths:
            # Save the stable list
            await cache.save_stable_list(session_id, inline_paths)
            logger.info(f"Saved stable list with {len(inline_paths)} inline files")

            # On first call, send all inline files
            files_to_send = [(p, c, t) for p, c, t in file_data if p in inline_paths]

            # Update sent file info
            for file_path, _, _ in files_to_send:
                try:
                    stat = os.stat(file_path)
                    await cache.update_sent_file_info(
                        session_id, file_path, int(stat.st_size), int(stat.st_mtime_ns)
                    )
                except OSError:
                    pass
        else:
            # No overflow, send everything inline
            logger.info("All files fit inline, no stable list needed")
            files_to_send = file_data
            overflow_paths = []

            # Record baseline for change detection even when no overflow
            for file_path, _, _ in files_to_send:
                try:
                    stat = os.stat(file_path)
                    await cache.update_sent_file_info(
                        session_id, file_path, int(stat.st_size), int(stat.st_mtime_ns)
                    )
                except OSError:
                    pass
    else:
        # Subsequent call - only send changed files
        logger.info(f"Using existing stable list for session {session_id}")

        files_to_send = []
        overflow_paths = []

        # Check each file in context
        for file_path in all_files:
            if file_path in stable_list:
                # This file should go inline
                if await cache.file_changed_since_last_send(session_id, file_path):
                    # File has changed, need to resend it
                    file_data = load_specific_files([file_path])
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
                # This file goes to vector store
                overflow_paths.append(file_path)

        logger.info(f"Sending {len(files_to_send)} changed files inline")

    # Add attachments to overflow (they always go to vector store)
    if attachments:
        attachment_files = gather_file_paths(attachments, skip_safety_check=True)
        overflow_paths.extend(attachment_files)
        logger.info(f"Added {len(attachment_files)} attachment files to vector store")

    return files_to_send, overflow_paths

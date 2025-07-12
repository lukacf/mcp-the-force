"""
Shared context loading functionality for file gathering and token counting.
"""

from pathlib import Path
from typing import List, Tuple

from .fs import gather_file_paths
from .token_counter import count_tokens


def load_specific_files(file_paths: List[str]) -> List[Tuple[str, str, int]]:
    """
    Load specific text files directly without additional gathering/filtering.

    Args:
        file_paths: List of exact file paths to load

    Returns:
        List of tuples containing (file_path, content, token_count)
    """
    import logging

    logger = logging.getLogger(__name__)
    result: List[Tuple[str, str, int]] = []

    for path in file_paths:
        try:
            # Read file content with UTF-8 encoding, ignoring errors
            content = Path(path).read_text(encoding="utf-8", errors="ignore")

            # Remove null bytes which can cause issues
            content = content.replace("\x00", "")

            # Count tokens for this content
            token_count = count_tokens([content])

            result.append((path, content, token_count))

        except Exception as e:
            # Log the error before skipping
            logger.warning(f"Failed to read file {path}: {type(e).__name__}: {e}")
            continue

    return result


def load_text_files(items: List[str]) -> List[Tuple[str, str, int]]:
    """
    Load text files and return their paths, contents, and token counts.

    This function uses the same file gathering and filtering logic as the
    prompt builder, ensuring consistency across the application.

    Args:
        items: List of file paths or directory paths to process

    Returns:
        List of tuples containing (file_path, content, token_count)
        Binary files, oversized files, and gitignored files are automatically
        filtered out by gather_file_paths.
    """
    import os
    import logging

    logger = logging.getLogger(__name__)

    # Debug: Log current working directory and user
    logger.info(
        f"DEBUG load_text_files: CWD={os.getcwd()}, USER={os.getenv('USER', 'unknown')}, UID={os.getuid()}"
    )
    logger.info(f"DEBUG load_text_files: Input items={items}")

    # Always use gather_file_paths to robustly handle files, directories,
    # and filtering in one place. This avoids race conditions with file
    # existence checks in Docker volume mounts.
    paths = gather_file_paths(items)
    logger.info(
        f"DEBUG load_text_files: gather_file_paths returned {len(paths)} paths: {paths}"
    )

    result: List[Tuple[str, str, int]] = []

    for path in paths:
        try:
            # Debug: Check file existence and permissions
            abs_path = os.path.abspath(path)
            logger.info(
                f"DEBUG load_text_files: Processing path '{path}' | abs_path '{abs_path}'"
            )

            if os.path.exists(abs_path):
                stat = os.stat(abs_path)
                logger.info(
                    f"DEBUG load_text_files: File exists! size={stat.st_size}, mode={oct(stat.st_mode)}, uid={stat.st_uid}, gid={stat.st_gid}"
                )
            else:
                logger.warning(
                    f"DEBUG load_text_files: File does NOT exist at '{abs_path}'"
                )

                # Also check the raw path
                if os.path.exists(path):
                    logger.warning(
                        f"DEBUG load_text_files: But file DOES exist at raw path '{path}'"
                    )

                # List parent directory to debug
                parent = os.path.dirname(abs_path) or "/"
                if os.path.exists(parent):
                    try:
                        items_in_parent = os.listdir(parent)
                        logger.info(
                            f"DEBUG load_text_files: Parent dir '{parent}' contains: {items_in_parent[:10]}..."
                        )  # First 10 items
                    except Exception as e:
                        logger.warning(
                            f"DEBUG load_text_files: Cannot list parent dir: {e}"
                        )
                continue

            # Read file content with UTF-8 encoding, ignoring errors
            content = Path(path).read_text(encoding="utf-8", errors="ignore")
            logger.info(
                f"DEBUG load_text_files: Successfully read {len(content)} chars from {path}"
            )

            # Remove null bytes which can cause issues
            content = content.replace("\x00", "")

            # Count tokens for this content
            token_count = count_tokens([content])

            result.append((path, content, token_count))

        except Exception as e:
            # Log the error before skipping
            logger.warning(f"Failed to read file {path}: {type(e).__name__}: {e}")
            continue

    return result

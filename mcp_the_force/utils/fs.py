import mimetypes
import os
import fnmatch
from pathlib import Path
from typing import List, Set
import logging
import time
from .thread_pool import run_in_thread_pool
from ..config import get_settings

logger = logging.getLogger(__name__)

# Common binary/generated file extensions to skip
BINARY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".a",
    ".lib",
    ".bin",
    ".obj",
    ".o",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".ico",
    ".tiff",
    ".webp",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".wav",
    ".flac",
    ".ogg",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".7z",
    ".rar",
    ".xz",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".sqlite",
    ".db",
    ".sqlite3",
    ".pyc",
    ".pyo",
    ".pyd",
    ".class",
    ".jar",
    ".node",
    ".wasm",
}

# Common text file extensions (for faster detection)
TEXT_EXTENSIONS = {
    # Text-based formats suitable for code analysis (subset of OpenAI supported formats):
    ".c",
    ".cpp",
    ".css",
    ".csv",
    ".go",
    ".html",
    ".java",
    ".js",
    ".json",
    ".md",
    ".php",
    ".py",
    ".rb",
    ".tex",
    ".ts",
    ".txt",
    ".xml",
}

# Common directories to skip (even if not in .gitignore)
SKIP_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "node_modules",
    ".npm",
    ".yarn",
    "bower_components",
    ".git",
    ".svn",
    ".hg",
    ".bzr",
    "venv",
    ".venv",
    "env",
    ".env",
    "virtualenv",
    "build",
    "dist",
    "target",
    "out",
    "bin",
    "obj",
    ".next",
    ".nuxt",
    ".cache",
    ".tmp",
    "tmp",
    "coverage",
    "htmlcov",
    ".coverage",
    ".idea",
    ".vscode",
    ".vs",
    "Pods",
    "DerivedData",
}

# File size limits are now configured in settings
# Get them when needed via get_settings().mcp.max_file_size


def _parse_gitignore(gitignore_path: Path) -> List[str]:
    """Parse .gitignore file and return list of patterns."""
    if not gitignore_path.exists():
        return []

    patterns = []
    try:
        with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    except Exception:
        pass
    return patterns


def _is_ignored(
    file_path: Path, gitignore_patterns: List[str], root_path: Path
) -> bool:
    """Check if file matches any gitignore pattern."""
    try:
        # Get relative path from root
        rel_path = file_path.relative_to(root_path)
        rel_path_str = rel_path.as_posix()

        for pattern in gitignore_patterns:
            # Handle negation patterns (starting with !)
            if pattern.startswith("!"):
                continue  # Skip negation for now (complex to implement correctly)

            # Handle directory patterns (ending with /)
            if pattern.endswith("/"):
                if any(part == pattern[:-1] for part in rel_path.parts):
                    return True
            else:
                # Use fnmatch for glob-style patterns
                if fnmatch.fnmatch(rel_path_str, pattern):
                    return True
                if fnmatch.fnmatch(file_path.name, pattern):
                    return True
                # Check if any parent directory matches
                if any(fnmatch.fnmatch(part, pattern) for part in rel_path.parts):
                    return True
    except (ValueError, OSError):
        pass

    return False


def _is_safe_path(base: Path, target: Path) -> bool:
    """Return True if target is not in the blacklist.

    For MCP server usage, we use a blacklist approach since:
    - AI models are read-only
    - MCP server is local/containerized
    - Explicit file paths are provided by users
    - We want to allow full filesystem access except for sensitive system paths
    """
    from ..config import get_settings

    settings = get_settings()
    blacklist = settings.security.path_blacklist

    # Expand ~ in the target path first
    if isinstance(target, Path):
        target_str = str(target)
    else:
        target_str = target
    expanded_target = os.path.expanduser(target_str)

    # Resolve the target path
    try:
        resolved_target = Path(expanded_target).resolve()
    except Exception:
        # If we can't resolve, err on the side of caution
        return False

    # Convert to string for comparison
    target_str = str(resolved_target)

    # Check if the target starts with any blacklisted path
    for blocked_path in blacklist:
        # Expand ~ in the blocked path
        expanded_blocked = os.path.expanduser(blocked_path)
        # Normalize the path for comparison
        normalized_blocked = os.path.normpath(expanded_blocked)

        # Ensure the blocked path ends with a separator to avoid partial matches
        # e.g., /home shouldn't block /home/user/project
        if not normalized_blocked.endswith(os.sep):
            normalized_blocked += os.sep

        # Check if target starts with the blocked path
        if target_str.startswith(
            normalized_blocked
        ) or target_str == normalized_blocked.rstrip(os.sep):
            logger.debug(f"Path {target} blocked by blacklist entry: {blocked_path}")
            return False

    return True


def _should_skip_dir(dir_path: Path) -> bool:
    """Check if directory should be skipped."""
    return dir_path.name in SKIP_DIRS or dir_path.name.startswith(".")


def _is_text_file(file_path: Path) -> bool:
    """Determine if file is likely a text file."""

    # Check extension first (fastest)
    ext = file_path.suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return False
    if ext in TEXT_EXTENSIONS:
        return True

    # Check mimetype
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type:
        if mime_type.startswith("text/"):
            return True
        if mime_type in [
            "application/json",
            "application/xml",
            "application/javascript",
        ]:
            return True
        if "text" in mime_type:
            return True

    # For files without extension or unknown mime type, check content
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(8192)  # Read first 8KB
            if b"\0" in chunk:  # Binary files often contain null bytes
                return False
            # Try to decode as text
            try:
                chunk.decode("utf-8")
                return True
            except UnicodeDecodeError:
                try:
                    chunk.decode("latin-1")
                    return True
                except UnicodeDecodeError:
                    return False
    except (OSError, IOError):
        return False

    return False


def gather_file_paths(items: List[str], skip_safety_check: bool = False) -> List[str]:
    """
    Gather text file paths from given items, respecting .gitignore and common patterns.

    Args:
        items: List of file or directory paths (should be absolute paths)
        skip_safety_check: If True, skip the project root safety check (for attachments)

    Returns:
        List of text file paths that should be included

    Note:
        Relative paths will be resolved relative to the MCP server's working directory,
        which may not be what you expect. Use absolute paths for reliable results.
    """
    if not items:
        logger.warning("gather_file_paths called with empty items list")
        return []

    # Get configured limits
    settings = get_settings()
    max_file_size = settings.mcp.max_file_size
    max_total_size = settings.mcp.max_total_size

    start_time = time.time()
    logger.info(
        f"[FS] gather_file_paths called with {len(items)} items: {items}, skip_safety_check={skip_safety_check}"
    )
    logger.debug(
        f"[FS] File size limits: max_file_size={max_file_size/1024/1024:.1f}MB, max_total_size={max_total_size/1024/1024:.1f}MB"
    )

    project_root = Path.cwd()
    logger.debug(
        f"DEBUG gather_file_paths: CWD/project_root={project_root}, UID={os.getuid()}, USER={os.getenv('USER', 'unknown')}, EUID={os.geteuid()}"
    )

    seen: Set[str] = set()
    out: List[str] = []
    total_size = 0

    for item in items:
        if total_size >= max_total_size:
            logger.warning(
                f"[FS] Reached total size limit ({max_total_size/1024/1024:.1f}MB), stopping"
            )
            break

        # Check for common relative path patterns and warn
        if item in [".", ".."] or item.startswith("./") or item.startswith("../"):
            # This is a relative path that may not work as expected
            # Continue processing but user should be aware
            pass

        raw_path = Path(item).expanduser()
        logger.info(f"[FS] Processing item '{item}' -> raw_path='{raw_path}'")

        if skip_safety_check:
            is_safe = True
            logger.info(f"[FS] Skipping safety check for attachment: {raw_path}")
        else:
            is_safe = _is_safe_path(project_root, raw_path)
            logger.debug(
                f"DEBUG gather_file_paths: _is_safe_path returned {is_safe} for {raw_path}"
            )

        if not is_safe:
            logger.warning(f"Skipping unsafe path outside project root: {raw_path}")
            continue

        try:
            path = raw_path.resolve()
        except (OSError, FileNotFoundError) as e:
            logger.warning(
                f"DEBUG gather_file_paths: Could not resolve path '{raw_path}': {e}"
            )
            continue

        logger.debug(
            f"DEBUG gather_file_paths: Resolved path='{path}', exists={path.exists()}"
        )

        if not path.exists():
            logger.warning(f"DEBUG gather_file_paths: Path does not exist: '{path}'")
            # Check if the original item exists without resolve
            if Path(item).exists():
                logger.warning(
                    f"DEBUG gather_file_paths: But original item DOES exist: '{item}'"
                )
            continue

        if path.is_file():
            # Single file
            logger.info(f"[FS] Processing file: {path}")
            try:
                # Check file size first
                try:
                    file_size = path.stat().st_size
                    if file_size > max_file_size:
                        logger.warning(
                            f"[FS] Skipping file {path} - too large ({file_size/1024/1024:.1f}MB > {max_file_size/1024/1024:.1f}MB limit)"
                        )
                        continue
                except OSError as e:
                    logger.warning(f"[FS] Could not stat file {path}: {e}")
                    continue

                is_text = _is_text_file(path)
                logger.info(
                    f"[FS] Is text file: {is_text}, size: {file_size/1024:.1f}KB"
                )
                if is_text:
                    path_str = str(path)
                    if path_str not in seen:
                        seen.add(path_str)
                        out.append(path_str)
                        logger.info(f"[FS] Added file {path_str} to output")
                        total_size += file_size
                else:
                    logger.info(f"[FS] Skipped non-text file: {path}")
            except (OSError, PermissionError) as e:
                logger.warning(f"Skipping {path} due to permission error: {e}")
                continue

        elif path.is_dir():
            # Directory - find .gitignore files
            gitignore_patterns = []

            # Look for .gitignore in current and parent directories
            current = path
            while current != current.parent:
                gitignore = current / ".gitignore"
                if gitignore.exists():
                    gitignore_patterns.extend(_parse_gitignore(gitignore))
                    break  # Use the first .gitignore found going up
                current = current.parent

            # Walk directory tree
            try:
                for root, dirs, files in os.walk(path):
                    if total_size >= max_total_size:
                        break

                    root_path = Path(root)

                    # Filter directories in-place to skip unwanted ones
                    dirs[:] = [d for d in dirs if not _should_skip_dir(root_path / d)]

                    # Process files
                    for file_name in files:
                        if total_size >= max_total_size:
                            break

                        file_path = root_path / file_name

                        # Skip if ignored by gitignore
                        if gitignore_patterns and _is_ignored(
                            file_path, gitignore_patterns, path
                        ):
                            continue

                        # Check if it's a text file we want
                        try:
                            # Check file size first
                            try:
                                file_size = file_path.stat().st_size
                                if file_size > max_file_size:
                                    logger.debug(
                                        f"[FS] Skipping file {file_path} - too large ({file_size/1024/1024:.1f}MB)"
                                    )
                                    continue
                            except OSError:
                                continue

                            if _is_text_file(file_path):
                                file_path_str = str(file_path)
                                if file_path_str not in seen:
                                    seen.add(file_path_str)
                                    out.append(file_path_str)
                                    total_size += file_size
                        except (OSError, PermissionError) as e:
                            logger.warning(
                                f"Skipping {file_path} due to permission error: {e}"
                            )

            except (OSError, PermissionError):
                # Skip directories we can't read
                continue

    result = sorted(out)  # Return sorted for consistent ordering
    logger.info(
        f"gather_file_paths completed in {time.time() - start_time:.2f}s - found {len(result)} files, total size: {total_size / 1024 / 1024:.2f}MB"
    )
    return result


async def gather_file_paths_async(
    items: List[str], skip_safety_check: bool = False
) -> List[str]:
    """Asynchronously gather file paths to avoid blocking the event loop."""
    result: List[str] = await run_in_thread_pool(
        gather_file_paths, items, skip_safety_check
    )
    return result

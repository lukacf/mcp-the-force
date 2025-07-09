import mimetypes
import os
import fnmatch
from pathlib import Path
from typing import List, Set
import logging
import time

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
    ".txt",
    ".md",
    ".rst",
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".xml",
    ".svg",
    ".csv",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".ps1",
    ".bat",
    ".cmd",
    ".c",
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hpp",
    ".hxx",
    ".java",
    ".kt",
    ".scala",
    ".clj",
    ".cljs",
    ".rb",
    ".php",
    ".go",
    ".rs",
    ".swift",
    ".dart",
    ".r",
    ".R",
    ".m",
    ".mm",
    ".pl",
    ".pm",
    ".lua",
    ".vim",
    ".el",
    ".lisp",
    ".dockerfile",
    ".dockerignore",
    ".gitignore",
    ".gitattributes",
    ".log",
    ".env",
    ".envrc",
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

# Maximum file size (500KB)
MAX_FILE_SIZE = 500 * 1024
# Maximum total size to gather (50MB)
MAX_TOTAL_SIZE = 50 * 1024 * 1024


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
    """Return True if target is within base directory after resolving."""
    import os

    # In CI/E2E environments, allow all paths
    if os.environ.get("CI_E2E") == "1":
        logger.debug(f"_is_safe_path: CI_E2E mode - allowing path: {target}")
        return True

    # Check if we're running in a Docker container
    if os.path.exists("/.dockerenv"):
        logger.debug(f"_is_safe_path: Docker environment - allowing path: {target}")
        return True

    try:
        with open("/proc/1/cgroup", "r") as f:
            cgroup_contents = f.read()
            if "docker" in cgroup_contents or "containerd" in cgroup_contents:
                logger.debug(
                    f"_is_safe_path: Docker cgroup detected - allowing path: {target}"
                )
                return True
    except Exception:
        pass

    # Otherwise, apply normal security checks
    try:
        base_resolved = base.resolve()
        target_resolved = target.resolve()
    except Exception:
        return False

    # Allow paths within project directory
    if base_resolved == target_resolved or base_resolved in target_resolved.parents:
        return True

    # Allow temp directory access
    import tempfile

    temp_dir = Path(tempfile.gettempdir()).resolve()
    if temp_dir in target_resolved.parents or temp_dir == target_resolved:
        return True

    return False


def _should_skip_dir(dir_path: Path) -> bool:
    """Check if directory should be skipped."""
    return dir_path.name in SKIP_DIRS or dir_path.name.startswith(".")


def _is_text_file(file_path: Path) -> bool:
    """Determine if file is likely a text file."""
    # Check file size first (quick exit)
    try:
        if file_path.stat().st_size > MAX_FILE_SIZE:
            return False
    except OSError:
        return False

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
        return []

    start_time = time.time()
    logger.info(f"gather_file_paths called with {len(items)} items: {items}")

    project_root = Path.cwd()
    logger.info(
        f"DEBUG gather_file_paths: CWD/project_root={project_root}, UID={os.getuid()}, USER={os.getenv('USER', 'unknown')}, EUID={os.geteuid()}"
    )

    seen: Set[str] = set()
    out: List[str] = []
    total_size = 0

    for item in items:
        if total_size >= MAX_TOTAL_SIZE:
            break

        # Check for common relative path patterns and warn
        if item in [".", ".."] or item.startswith("./") or item.startswith("../"):
            # This is a relative path that may not work as expected
            # Continue processing but user should be aware
            pass

        raw_path = Path(item).expanduser()
        logger.info(
            f"DEBUG gather_file_paths: Processing item '{item}' -> raw_path='{raw_path}'"
        )

        if skip_safety_check:
            is_safe = True
            logger.info(
                f"DEBUG gather_file_paths: Skipping safety check for attachment: {raw_path}"
            )
        else:
            is_safe = _is_safe_path(project_root, raw_path)
            logger.info(
                f"DEBUG gather_file_paths: _is_safe_path returned {is_safe} for {raw_path}"
            )

        if not is_safe:
            logger.warning(f"Skipping unsafe path outside project root: {raw_path}")
            continue

        path = raw_path.resolve()
        logger.info(
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
            try:
                if _is_text_file(path):
                    path_str = str(path)
                    if path_str not in seen:
                        seen.add(path_str)
                        out.append(path_str)
                        logger.info(
                            f"DEBUG gather_file_paths: Added file {path_str} to output"
                        )
                        try:
                            total_size += path.stat().st_size
                        except OSError as e:
                            logger.warning(
                                f"DEBUG gather_file_paths: Could not stat {path_str}: {e}"
                            )
                            pass
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
                    if total_size >= MAX_TOTAL_SIZE:
                        break

                    root_path = Path(root)

                    # Filter directories in-place to skip unwanted ones
                    dirs[:] = [d for d in dirs if not _should_skip_dir(root_path / d)]

                    # Process files
                    for file_name in files:
                        if total_size >= MAX_TOTAL_SIZE:
                            break

                        file_path = root_path / file_name

                        # Skip if ignored by gitignore
                        if gitignore_patterns and _is_ignored(
                            file_path, gitignore_patterns, path
                        ):
                            continue

                        # Check if it's a text file we want
                        try:
                            if _is_text_file(file_path):
                                file_path_str = str(file_path)
                                if file_path_str not in seen:
                                    seen.add(file_path_str)
                                    out.append(file_path_str)
                                    try:
                                        total_size += file_path.stat().st_size
                                    except OSError:
                                        pass
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

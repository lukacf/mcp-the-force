"""Image loading utility for vision-capable models."""

import asyncio
import ipaddress
import logging
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

# Network timeouts (seconds)
_CONNECT_TIMEOUT = 10
_READ_TIMEOUT = 30
_TOTAL_TIMEOUT = 60
_DNS_TIMEOUT = 5

# Maximum redirects to follow
_MAX_REDIRECTS = 5

# Chunk size for streaming downloads (64KB)
_DOWNLOAD_CHUNK_SIZE = 64 * 1024

# Maximum total memory for all images (200MB)
_MAX_TOTAL_MEMORY_BYTES = 200 * 1024 * 1024


class ImageLoadError(Exception):
    """Error loading an image."""

    pass


@dataclass
class LoadedImage:
    """A loaded image ready for API submission."""

    data: bytes
    mime_type: str
    source: str  # 'file' or 'url'
    original_path: str


# Magic bytes for image format detection
_MAGIC_BYTES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
}

# Extension to MIME type mapping
_EXTENSION_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# Supported MIME types
_SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# Blocked private/internal IP ranges (SSRF protection)
_PRIVATE_IP_RANGES = [
    ipaddress.ip_network("0.0.0.0/8"),  # "This" network
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),  # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("192.88.99.0/24"),  # 6to4 relay
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),  # Benchmark testing
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    # IPv6
    ipaddress.ip_network("::1/128"),  # Loopback
    ipaddress.ip_network("::/128"),  # Unspecified
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped (check underlying IPv4)
    ipaddress.ip_network("64:ff9b::/96"),  # IPv4/IPv6 translation
    ipaddress.ip_network("100::/64"),  # Discard prefix
    ipaddress.ip_network("2001::/32"),  # Teredo
    ipaddress.ip_network("2001:10::/28"),  # ORCHID
    ipaddress.ip_network("2001:20::/28"),  # ORCHIDv2
    ipaddress.ip_network("2001:db8::/32"),  # Documentation
    ipaddress.ip_network("2002::/16"),  # 6to4
    ipaddress.ip_network("fc00::/7"),  # Unique local
    ipaddress.ip_network("fe80::/10"),  # Link-local
    ipaddress.ip_network("ff00::/8"),  # Multicast
]


def _normalize_ip(
    ip_str: str,
) -> Optional[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Normalize an IP address string to a canonical form.

    Handles various bypass attempts:
    - Hex encoding: 0x7f.0x00.0x00.0x01
    - Octal encoding: 0177.0.0.1
    - Decimal encoding: 2130706433
    - IPv6 zone IDs: ::1%eth0
    - IPv4-mapped IPv6: ::ffff:127.0.0.1

    Args:
        ip_str: IP address string in any format

    Returns:
        Normalized IP address object, or None if invalid
    """
    # Strip IPv6 zone ID (e.g., ::1%eth0 -> ::1)
    if "%" in ip_str:
        ip_str = ip_str.split("%")[0]

    # Strip brackets from IPv6
    ip_str = ip_str.strip("[]")

    # Try parsing as-is first (handles most cases)
    try:
        ip = ipaddress.ip_address(ip_str)

        # Check for IPv4-mapped IPv6 addresses
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            return ip.ipv4_mapped

        return ip
    except ValueError:
        pass

    # Handle pure decimal IPv4 format (e.g., 2130706433 = 127.0.0.1)
    # Python's ipaddress doesn't handle pure decimal strings
    if ip_str.isdigit():
        try:
            decimal_value = int(ip_str)
            if 0 <= decimal_value <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(decimal_value)
        except (ValueError, OverflowError):
            pass

    # Handle hex/octal IPv4 formats like 0x7f.0.0.1 or 0177.0.0.1
    # Split by dots and try to parse each octet
    parts = ip_str.split(".")
    if len(parts) == 4:
        try:
            octets = []
            for part in parts:
                part = part.strip()
                if part.lower().startswith("0x"):
                    octets.append(int(part, 16))
                elif part.startswith("0") and len(part) > 1 and part.isdigit():
                    octets.append(int(part, 8))
                else:
                    octets.append(int(part))

            if all(0 <= o <= 255 for o in octets):
                return ipaddress.IPv4Address(
                    (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]
                )
        except (ValueError, OverflowError):
            pass

    return None


def _is_private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address is in a private/internal range.

    Args:
        ip: Normalized IP address object

    Returns:
        True if IP is private/internal, False otherwise
    """
    # Check IPv4-mapped IPv6 addresses
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped

    for network in _PRIVATE_IP_RANGES:
        try:
            if ip in network:
                return True
        except TypeError:
            # IPv4/IPv6 mismatch, skip
            continue

    return False


def _is_private_ip_str(ip_str: str) -> bool:
    """Check if an IP address string is in a private/internal range.

    Handles various encoding bypass attempts.

    Args:
        ip_str: IP address string in any format

    Returns:
        True if IP is private/internal or invalid, False otherwise
    """
    ip = _normalize_ip(ip_str)
    if ip is None:
        # Invalid IP - treat as potentially dangerous
        return True

    return _is_private_ip(ip)


async def _resolve_hostname(hostname: str) -> List[str]:
    """Resolve hostname to IP addresses asynchronously.

    Args:
        hostname: Hostname to resolve

    Returns:
        List of resolved IP addresses (sorted for determinism)

    Raises:
        ImageLoadError: If resolution fails or times out
    """
    loop = asyncio.get_event_loop()

    try:
        # Run DNS resolution in thread pool with timeout
        results = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: socket.getaddrinfo(
                    hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
                ),
            ),
            timeout=_DNS_TIMEOUT,
        )

        # Extract unique IP addresses and sort for deterministic ordering
        # Using a set for uniqueness, then sorting for reproducibility
        ips = sorted({result[4][0] for result in results})
        return ips

    except asyncio.TimeoutError:
        raise ImageLoadError(
            f"DNS resolution timeout for '{hostname}' (limit: {_DNS_TIMEOUT}s)"
        )
    except socket.gaierror as e:
        raise ImageLoadError(f"Failed to resolve hostname '{hostname}': {e}")


def _validate_url_structure(url: str) -> Tuple[str, str, int]:
    """Validate URL structure and extract components.

    Args:
        url: URL to validate

    Returns:
        Tuple of (scheme, hostname, port)

    Raises:
        ImageLoadError: If URL structure is invalid
    """
    try:
        parsed = urlparse(url)
    except ValueError as e:
        raise ImageLoadError(f"Malformed URL '{url}': {e}")

    # Only allow http/https
    if parsed.scheme not in ("http", "https"):
        raise ImageLoadError(
            f"Invalid URL scheme '{parsed.scheme}'. Only http/https allowed."
        )

    # Block URLs without hostname
    if not parsed.hostname:
        raise ImageLoadError(f"Invalid URL: no hostname found in '{url}'")

    hostname = parsed.hostname.lower()

    # Strip IPv6 zone ID from hostname
    if "%" in hostname:
        hostname = hostname.split("%")[0]

    # Block localhost variations (including encoded forms)
    localhost_patterns = [
        "localhost",
        "localhost.localdomain",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "0",
        "0x7f.0.0.1",  # Hex localhost
        "0x7f000001",  # Hex decimal localhost
        "2130706433",  # Decimal localhost
        "0177.0.0.1",  # Octal localhost
        "[::1]",
        "[::ffff:127.0.0.1]",
    ]
    if hostname in localhost_patterns:
        raise ImageLoadError(
            f"URLs to localhost are not allowed for security reasons: {url}"
        )

    # Check if hostname looks like an IP address
    ip = _normalize_ip(hostname)
    if ip is not None and _is_private_ip(ip):
        raise ImageLoadError(
            f"URLs to private/internal IPs are not allowed for security reasons: {url}"
        )

    # Block internal/metadata endpoints
    blocked_hostnames = [
        "metadata.google.internal",
        "metadata.google.com",
        "169.254.169.254",
        "metadata",
        "kubernetes.default",
        "kubernetes.default.svc",
        "kubernetes.default.svc.cluster.local",
        "host.docker.internal",
        "gateway.docker.internal",
    ]
    if hostname in blocked_hostnames:
        raise ImageLoadError(
            f"URLs to internal services are not allowed for security reasons: {url}"
        )

    # Block hostnames ending with suspicious patterns
    blocked_suffixes = [
        ".internal",
        ".local",
        ".localhost",
        ".localdomain",
    ]
    for suffix in blocked_suffixes:
        if hostname.endswith(suffix):
            raise ImageLoadError(
                f"URLs to internal hostnames are not allowed for security reasons: {url}"
            )

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    return parsed.scheme, hostname, port


async def _validate_and_resolve_url(url: str) -> Tuple[str, List[str], int]:
    """Validate URL and resolve hostname to IPs.

    Performs DNS resolution and validates all resolved IPs.

    Args:
        url: URL to validate

    Returns:
        Tuple of (hostname, resolved_ips, port)

    Raises:
        ImageLoadError: If URL is blocked or resolution fails
    """
    scheme, hostname, port = _validate_url_structure(url)

    # Check if hostname is already an IP
    ip = _normalize_ip(hostname)
    if ip is not None:
        if _is_private_ip(ip):
            raise ImageLoadError(
                f"URLs to private/internal IPs are not allowed for security reasons: {url}"
            )
        return hostname, [str(ip)], port

    # Resolve hostname to IPs
    resolved_ips = await _resolve_hostname(hostname)

    if not resolved_ips:
        raise ImageLoadError(f"No IP addresses found for hostname '{hostname}'")

    # Validate all resolved IPs
    for ip_str in resolved_ips:
        if _is_private_ip_str(ip_str):
            raise ImageLoadError(
                f"URL resolves to private/internal IP ({ip_str}): {url}"
            )

    return hostname, resolved_ips, port


def detect_mime_type(data: bytes, filename: str) -> str:
    """Detect MIME type from magic bytes or file extension.

    Args:
        data: Image data bytes
        filename: Original filename for extension fallback

    Returns:
        MIME type string (e.g., 'image/png')

    Raises:
        ImageLoadError: If format cannot be detected or is unsupported
    """
    # Check magic bytes first
    for magic, mime_type in _MAGIC_BYTES.items():
        if data.startswith(magic):
            return mime_type

    # Special case for WebP (RIFF....WEBP)
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"

    # Fall back to extension
    ext = Path(filename).suffix.lower()
    if ext in _EXTENSION_MIME:
        return _EXTENSION_MIME[ext]

    raise ImageLoadError(
        f"Unsupported image format for '{filename}'. "
        f"Supported formats: JPEG, PNG, GIF, WebP"
    )


def _is_url(path: str) -> bool:
    """Check if path is a URL."""
    return path.startswith("http://") or path.startswith("https://")


# Sensitive directories that should never be accessed
_SENSITIVE_DIRS = [
    # Unix/Linux system directories
    "/etc",
    "/var/log",
    "/var/run",
    "/var/lib",
    "/var/spool",
    "/root",
    "/proc",
    "/sys",
    "/dev",
    "/boot",
    "/lib",
    "/lib64",
    "/usr/lib",
    "/usr/local/lib",
    "/sbin",
    "/usr/sbin",
    # macOS system directories
    "/private/etc",
    "/private/var/log",
    "/private/var/run",
    "/private/var/db",
    "/private/var/root",
    "/System",
    "/Library/Keychains",
    "/Library/Security",
    # User sensitive directories (will be expanded with home dir)
    "/.ssh",
    "/.aws",
    "/.gnupg",
    "/.config/gcloud",
    "/.kube",
    "/.docker",
    "/.azure",
    "/.credentials",
    "/.secrets",
    "/.netrc",
    "/.npmrc",
    "/.pypirc",
]

# Hidden directories that are always blocked at root level
_BLOCKED_HIDDEN_DIRS = {
    ".ssh",
    ".aws",
    ".gnupg",
    ".gcloud",
    ".kube",
    ".docker",
    ".azure",
    ".credentials",
    ".secrets",
    ".password-store",
    ".mozilla",
    ".chrome",
    ".config",  # Block entire .config for safety
}


def _validate_file_path(path: str) -> Path:
    """Validate file path for path traversal protection.

    Args:
        path: File path to validate

    Returns:
        Resolved absolute Path object

    Raises:
        ImageLoadError: If path is blocked due to security concerns
    """
    file_path = Path(path)

    # Block path traversal in original path BEFORE any resolution
    # This catches things like "../../../etc/passwd" early
    normalized = str(file_path).replace("\\", "/")
    if ".." in normalized:
        raise ImageLoadError(
            f"Path traversal detected in '{path}': '..' sequences not allowed"
        )

    # Resolve to absolute path
    # Note: resolve() follows symlinks which is actually what we want
    # to catch symlink-based attacks pointing to sensitive locations
    try:
        resolved = file_path.resolve(strict=False)
    except (OSError, ValueError) as e:
        raise ImageLoadError(f"Invalid file path '{path}': {e}")

    resolved_str = str(resolved)

    # Check against sensitive directories
    for sensitive_dir in _SENSITIVE_DIRS:
        # Handle both absolute sensitive dirs and home-relative ones
        if sensitive_dir.startswith("/"):
            check_dir = sensitive_dir
        else:
            # Expand home-relative paths
            check_dir = str(Path.home()) + sensitive_dir

        if resolved_str.startswith(check_dir + "/") or resolved_str == check_dir:
            raise ImageLoadError(
                f"Access to '{check_dir}' is blocked for security reasons"
            )

    # Block access to hidden directories at the system root level
    # e.g., /.ssh, but allow /home/user/.local/images/
    parts = resolved.parts
    if len(parts) >= 2:
        # Check if second part (first after root) is a blocked hidden dir
        first_dir = parts[1]
        if first_dir in _BLOCKED_HIDDEN_DIRS:
            raise ImageLoadError(
                f"Access to hidden system directory '/{first_dir}' is blocked for security reasons"
            )

        # Also check for hidden dirs under common user directories
        # Block things like /home/user/.ssh but allow /home/user/project/.git
        if len(parts) >= 4 and parts[1] in ("home", "Users", "private"):
            # This is a path like /home/user/something or /Users/user/something
            # Check if the 4th part is a blocked hidden dir (after home/user)
            if len(parts) > 3 and parts[3] in _BLOCKED_HIDDEN_DIRS:
                raise ImageLoadError(
                    f"Access to user sensitive directory '{parts[3]}' is blocked for security reasons"
                )

    # Verify the path exists (but don't follow symlinks for this check)
    # This prevents TOCTOU issues where a symlink could be created after validation
    try:
        # Use lstat to not follow symlinks
        if file_path.is_symlink():
            # For symlinks, verify the target is safe
            target = resolved
            # Re-check target against sensitive dirs (already done above via resolve)
            # This is a defense-in-depth check
            logger.debug(f"Path '{path}' is symlink pointing to '{target}'")
    except (OSError, ValueError):
        pass  # File might not exist yet, that's OK

    return resolved


async def _load_from_file(path: str, max_size_bytes: int) -> LoadedImage:
    """Load image from local file.

    Args:
        path: Local file path
        max_size_bytes: Maximum allowed file size

    Returns:
        LoadedImage with file contents

    Raises:
        ImageLoadError: If file not found, blocked, or exceeds size limit
    """
    # Path traversal protection: validate before accessing
    file_path = _validate_file_path(path)

    if not file_path.exists():
        raise ImageLoadError(f"File not found: {path}")

    # Check file size before loading
    try:
        file_size = file_path.stat().st_size
    except OSError as e:
        raise ImageLoadError(f"Cannot access file '{path}': {e}")

    if file_size > max_size_bytes:
        max_mb = max_size_bytes / (1024 * 1024)
        actual_mb = file_size / (1024 * 1024)
        raise ImageLoadError(
            f"Image '{path}' ({actual_mb:.1f}MB) exceeds {max_mb:.0f}MB limit"
        )

    # Load file contents
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, file_path.read_bytes)
    except (OSError, IOError) as e:
        raise ImageLoadError(f"Failed to read file '{path}': {e}")

    mime_type = detect_mime_type(data, path)

    return LoadedImage(
        data=data,
        mime_type=mime_type,
        source="file",
        original_path=path,
    )


class _SafeResolver:
    """Custom DNS resolver that returns pre-validated IPs.

    This prevents DNS rebinding attacks by ensuring we connect to the IPs
    we validated, not whatever DNS returns at connection time.
    """

    def __init__(self, hostname: str, resolved_ips: List[str], port: int):
        self.hostname = hostname
        self.resolved_ips = resolved_ips
        self.port = port

    async def resolve(
        self, host: str, port: int = 0, family: int = socket.AF_INET
    ) -> List[dict]:
        """Return pre-resolved IPs for the validated hostname."""
        # Only return our validated IPs for the original hostname
        if host.lower() == self.hostname.lower():
            results = []
            for ip_str in self.resolved_ips:
                ip = ipaddress.ip_address(ip_str)
                if isinstance(ip, ipaddress.IPv4Address):
                    if family in (socket.AF_INET, socket.AF_UNSPEC):
                        results.append(
                            {
                                "hostname": host,
                                "host": ip_str,
                                "port": port or self.port,
                                "family": socket.AF_INET,
                                "proto": 0,
                                "flags": socket.AI_NUMERICHOST,
                            }
                        )
                elif isinstance(ip, ipaddress.IPv6Address):
                    if family in (socket.AF_INET6, socket.AF_UNSPEC):
                        results.append(
                            {
                                "hostname": host,
                                "host": ip_str,
                                "port": port or self.port,
                                "family": socket.AF_INET6,
                                "proto": 0,
                                "flags": socket.AI_NUMERICHOST,
                            }
                        )
            if results:
                return results

        # For any other hostname (shouldn't happen), raise error
        raise OSError(f"DNS rebinding attempt blocked: unexpected hostname '{host}'")

    async def close(self) -> None:
        """Required by aiohttp but we have nothing to clean up."""
        pass


async def _load_from_url(url: str, max_size_bytes: int) -> LoadedImage:
    """Load image from URL with SSRF protection.

    This function implements comprehensive SSRF protection:
    1. Validates URL structure and blocks suspicious patterns
    2. Resolves DNS and validates all resolved IPs
    3. Uses a custom resolver to connect directly to validated IPs (prevents DNS rebinding)
    4. Disables automatic redirects and validates each redirect manually
    5. Uses streaming downloads to enforce size limits

    Args:
        url: HTTP/HTTPS URL
        max_size_bytes: Maximum allowed file size

    Returns:
        LoadedImage with downloaded contents

    Raises:
        ImageLoadError: If URL fetch fails, is blocked, or exceeds size limit
    """
    # Phase 1: Validate URL structure and resolve DNS
    original_url = url
    hostname, resolved_ips, port = await _validate_and_resolve_url(url)

    # Configure timeouts
    timeout = aiohttp.ClientTimeout(
        connect=_CONNECT_TIMEOUT,
        sock_read=_READ_TIMEOUT,
        total=_TOTAL_TIMEOUT,
    )

    redirect_count = 0
    current_url = url
    current_hostname = hostname
    current_resolved_ips = resolved_ips
    current_port = port

    try:
        while redirect_count <= _MAX_REDIRECTS:
            # Create a new safe resolver for current hostname
            # This is critical: each hostname needs its own resolver to prevent DNS rebinding
            safe_resolver = _SafeResolver(
                current_hostname, current_resolved_ips, current_port
            )
            connector = aiohttp.TCPConnector(
                resolver=safe_resolver,
                ttl_dns_cache=0,
                use_dns_cache=False,
            )

            async with aiohttp.ClientSession(
                timeout=timeout, connector=connector
            ) as session:
                # Disable automatic redirects to validate each redirect URL
                async with session.get(
                    current_url,
                    allow_redirects=False,
                    headers={
                        "Host": current_hostname
                    },  # Original hostname for virtual hosting
                ) as response:
                    # Handle redirects manually
                    if response.status in (301, 302, 303, 307, 308):
                        redirect_count += 1
                        if redirect_count > _MAX_REDIRECTS:
                            raise ImageLoadError(
                                f"Too many redirects ({_MAX_REDIRECTS}) fetching '{original_url}'"
                            )

                        location = response.headers.get("Location")
                        if not location:
                            raise ImageLoadError(
                                f"Redirect without Location header from '{current_url}'"
                            )

                        # Handle relative redirects
                        if not location.startswith(("http://", "https://")):
                            parsed = urlparse(current_url)
                            if location.startswith("/"):
                                location = (
                                    f"{parsed.scheme}://{parsed.netloc}{location}"
                                )
                            else:
                                location = (
                                    f"{parsed.scheme}://{parsed.netloc}/{location}"
                                )

                        # Validate redirect URL - prevents SSRF via redirect
                        # Also re-resolves DNS for the new hostname (if different)
                        logger.debug(f"Following redirect to: {location}")
                        (
                            current_hostname,
                            current_resolved_ips,
                            current_port,
                        ) = await _validate_and_resolve_url(location)
                        current_url = location
                        # Continue to next iteration, which creates a new session with new resolver
                        continue

                    if response.status != 200:
                        raise ImageLoadError(
                            f"Failed to fetch image from '{original_url}': HTTP {response.status}"
                        )

                    # Check Content-Length header (but don't trust it fully)
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        try:
                            declared_size = int(content_length)
                            if declared_size > max_size_bytes:
                                max_mb = max_size_bytes / (1024 * 1024)
                                actual_mb = declared_size / (1024 * 1024)
                                raise ImageLoadError(
                                    f"Image at '{original_url}' ({actual_mb:.1f}MB) exceeds {max_mb:.0f}MB limit"
                                )
                        except ValueError:
                            pass  # Invalid Content-Length, will check actual size

                    # Stream download with size checking
                    chunks = []
                    total_size = 0

                    async for chunk in response.content.iter_chunked(
                        _DOWNLOAD_CHUNK_SIZE
                    ):
                        total_size += len(chunk)
                        if total_size > max_size_bytes:
                            max_mb = max_size_bytes / (1024 * 1024)
                            raise ImageLoadError(
                                f"Image at '{original_url}' exceeds {max_mb:.0f}MB limit during download"
                            )
                        chunks.append(chunk)

                    data = b"".join(chunks)
                    # Successfully downloaded, exit the while loop
                    break

        else:
            # This shouldn't happen, but catch infinite loops
            raise ImageLoadError(
                f"Failed to download image from '{original_url}' after {_MAX_REDIRECTS} redirects"
            )

    except asyncio.TimeoutError:
        raise ImageLoadError(
            f"Timeout fetching image from '{original_url}' (limit: {_TOTAL_TIMEOUT}s)"
        )
    except aiohttp.ClientError as e:
        raise ImageLoadError(f"Failed to fetch image from '{original_url}': {e}")

    # Extract filename from URL for MIME detection fallback
    filename = url.split("/")[-1].split("?")[0] or "image.bin"
    mime_type = detect_mime_type(data, filename)

    return LoadedImage(
        data=data,
        mime_type=mime_type,
        source="url",
        original_path=original_url,
    )


async def load_images(
    paths: List[str],
    max_size_mb: float = 20.0,
    max_total_mb: float = 200.0,
    total_timeout: float = 120.0,
) -> List[LoadedImage]:
    """Load images from file paths or URLs.

    Images are loaded sequentially to enforce total memory limit during loading,
    preventing memory exhaustion before the limit check fires. Each image is
    checked against the running total immediately after loading.

    Args:
        paths: List of file paths or URLs
        max_size_mb: Maximum size per image in megabytes (default: 20MB)
        max_total_mb: Maximum total size for all images in megabytes (default: 200MB)
        total_timeout: Maximum total time for all images in seconds (default: 120s)

    Returns:
        List of LoadedImage objects

    Raises:
        ImageLoadError: If any image fails to load, times out, or exceeds limits
    """
    if not paths:
        return []

    max_size_bytes = int(max_size_mb * 1024 * 1024)
    max_total_bytes = int(max_total_mb * 1024 * 1024)

    # Quick sanity check: if max images * per-image limit could exceed total,
    # that's fine - we check actual sizes below. But if the user requests
    # an impossible configuration, warn them.
    if len(paths) * max_size_bytes > max_total_bytes * 10:
        logger.warning(
            f"Loading {len(paths)} images with per-image limit {max_size_mb}MB. "
            f"Total limit is {max_total_mb}MB - some images may fail."
        )

    async def _load_with_total_check() -> List[LoadedImage]:
        """Load images sequentially, checking total size after each load."""
        results: List[LoadedImage] = []
        running_total = 0

        for path in paths:
            # Load single image
            if _is_url(path):
                img = await _load_from_url(path, max_size_bytes)
            else:
                img = await _load_from_file(path, max_size_bytes)

            # Check running total BEFORE adding to results
            running_total += len(img.data)
            if running_total > max_total_bytes:
                total_mb = running_total / (1024 * 1024)
                raise ImageLoadError(
                    f"Total image size ({total_mb:.1f}MB) exceeds {max_total_mb:.0f}MB limit "
                    f"after loading '{path}'. Reduce the number of images or use smaller files."
                )

            results.append(img)

        return results

    # Run with overall timeout
    try:
        results = await asyncio.wait_for(
            _load_with_total_check(),
            timeout=total_timeout,
        )
    except asyncio.TimeoutError:
        raise ImageLoadError(
            f"Timeout loading {len(paths)} images (total limit: {total_timeout}s)"
        )

    total_size = sum(len(img.data) for img in results)
    logger.info(
        f"Loaded {len(results)} images, total size: {total_size / (1024 * 1024):.1f}MB"
    )

    return results

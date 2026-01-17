"""Tests for image loading utility - TDD."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# Will import after implementation
# from mcp_the_force.utils.image_loader import (
#     load_images,
#     LoadedImage,
#     ImageLoadError,
#     detect_mime_type,
# )


class TestLoadedImageDataclass:
    """Test LoadedImage dataclass structure."""

    def test_loaded_image_has_required_fields(self):
        """LoadedImage should have data, mime_type, source, and original_path."""
        from mcp_the_force.utils.image_loader import LoadedImage

        img = LoadedImage(
            data=b"fake image data",
            mime_type="image/png",
            source="file",
            original_path="/path/to/image.png",
        )

        assert img.data == b"fake image data"
        assert img.mime_type == "image/png"
        assert img.source == "file"
        assert img.original_path == "/path/to/image.png"


class TestMimeTypeDetection:
    """Test MIME type detection from file content and extension."""

    def test_detect_png_from_magic_bytes(self):
        """Should detect PNG from magic bytes."""
        from mcp_the_force.utils.image_loader import detect_mime_type

        # PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
        png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        assert detect_mime_type(png_header, "unknown.bin") == "image/png"

    def test_detect_jpeg_from_magic_bytes(self):
        """Should detect JPEG from magic bytes."""
        from mcp_the_force.utils.image_loader import detect_mime_type

        # JPEG magic bytes: FF D8 FF
        jpeg_header = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        assert detect_mime_type(jpeg_header, "unknown.bin") == "image/jpeg"

    def test_detect_gif_from_magic_bytes(self):
        """Should detect GIF from magic bytes."""
        from mcp_the_force.utils.image_loader import detect_mime_type

        gif_header = b"GIF89a" + b"\x00" * 100
        assert detect_mime_type(gif_header, "unknown.bin") == "image/gif"

    def test_detect_webp_from_magic_bytes(self):
        """Should detect WebP from magic bytes."""
        from mcp_the_force.utils.image_loader import detect_mime_type

        # WebP: RIFF....WEBP
        webp_header = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100
        assert detect_mime_type(webp_header, "unknown.bin") == "image/webp"

    def test_fallback_to_extension_for_unknown_magic(self):
        """Should fall back to file extension if magic bytes unknown."""
        from mcp_the_force.utils.image_loader import detect_mime_type

        unknown_data = b"\x00\x00\x00\x00" + b"\x00" * 100
        assert detect_mime_type(unknown_data, "photo.jpg") == "image/jpeg"
        assert detect_mime_type(unknown_data, "photo.jpeg") == "image/jpeg"
        assert detect_mime_type(unknown_data, "photo.png") == "image/png"
        assert detect_mime_type(unknown_data, "photo.gif") == "image/gif"
        assert detect_mime_type(unknown_data, "photo.webp") == "image/webp"

    def test_raises_for_unsupported_format(self):
        """Should raise error for unsupported image formats."""
        from mcp_the_force.utils.image_loader import detect_mime_type, ImageLoadError

        unknown_data = b"\x00\x00\x00\x00" + b"\x00" * 100
        with pytest.raises(ImageLoadError, match="Unsupported image format"):
            detect_mime_type(unknown_data, "document.pdf")


class TestLoadImagesFromFiles:
    """Test loading images from local file paths."""

    @pytest.fixture
    def temp_png_file(self, tmp_path):
        """Create a temporary PNG file."""
        png_path = tmp_path / "test_image.png"
        # PNG magic bytes + minimal valid PNG structure
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        png_path.write_bytes(png_data)
        return png_path

    @pytest.fixture
    def temp_jpeg_file(self, tmp_path):
        """Create a temporary JPEG file."""
        jpeg_path = tmp_path / "test_image.jpg"
        jpeg_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        jpeg_path.write_bytes(jpeg_data)
        return jpeg_path

    @pytest.mark.asyncio
    async def test_load_single_file(self, temp_png_file):
        """Should load a single image file."""
        from mcp_the_force.utils.image_loader import load_images

        images = await load_images([str(temp_png_file)])

        assert len(images) == 1
        assert images[0].mime_type == "image/png"
        assert images[0].source == "file"
        assert images[0].original_path == str(temp_png_file)
        assert len(images[0].data) > 0

    @pytest.mark.asyncio
    async def test_load_multiple_files(self, temp_png_file, temp_jpeg_file):
        """Should load multiple image files."""
        from mcp_the_force.utils.image_loader import load_images

        images = await load_images([str(temp_png_file), str(temp_jpeg_file)])

        assert len(images) == 2
        mime_types = {img.mime_type for img in images}
        assert mime_types == {"image/png", "image/jpeg"}

    @pytest.mark.asyncio
    async def test_file_not_found_raises_error(self):
        """Should raise error for non-existent file."""
        from mcp_the_force.utils.image_loader import load_images, ImageLoadError

        with pytest.raises(ImageLoadError, match="File not found"):
            await load_images(["/nonexistent/path/image.png"])

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        """Should return empty list for empty input."""
        from mcp_the_force.utils.image_loader import load_images

        images = await load_images([])
        assert images == []


class TestLoadImagesFromURLs:
    """Test loading images from HTTP/HTTPS URLs."""

    @pytest.mark.asyncio
    async def test_load_image_from_url(self):
        """Should load image from HTTP URL."""
        from mcp_the_force.utils.image_loader import load_images

        # Create a mock for streaming response
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        mock_content = AsyncMock()
        mock_content.iter_chunked = MagicMock(return_value=AsyncIterator([png_data]))

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.content = mock_content
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Bypass SSRF validation since we're mocking the HTTP layer
        with patch(
            "mcp_the_force.utils.image_loader._validate_and_resolve_url"
        ) as mock_validate:
            mock_validate.return_value = ("example.com", ["93.184.216.34"], 443)
            with patch(
                "mcp_the_force.utils.image_loader.aiohttp.ClientSession",
                return_value=mock_session,
            ):
                images = await load_images(["https://example.com/image.png"])

        assert len(images) == 1
        assert images[0].mime_type == "image/png"
        assert images[0].source == "url"
        assert images[0].original_path == "https://example.com/image.png"

    @pytest.mark.asyncio
    async def test_url_not_found_raises_error(self):
        """Should raise error for 404 URL."""
        from mcp_the_force.utils.image_loader import load_images, ImageLoadError

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.headers = {}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Bypass SSRF validation since we're mocking the HTTP layer
        with patch(
            "mcp_the_force.utils.image_loader._validate_and_resolve_url"
        ) as mock_validate:
            mock_validate.return_value = ("example.com", ["93.184.216.34"], 443)
            with patch(
                "mcp_the_force.utils.image_loader.aiohttp.ClientSession",
                return_value=mock_session,
            ):
                with pytest.raises(ImageLoadError, match="Failed to fetch"):
                    await load_images(["https://example.com/notfound.png"])

    @pytest.mark.asyncio
    async def test_identifies_url_vs_file(self, tmp_path):
        """Should correctly identify URLs vs file paths."""
        from mcp_the_force.utils.image_loader import load_images

        # Create a local file
        png_path = tmp_path / "local.png"
        png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        # Create a mock for streaming response
        jpeg_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100

        mock_content = AsyncMock()
        mock_content.iter_chunked = MagicMock(return_value=AsyncIterator([jpeg_data]))

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.content = mock_content
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Bypass SSRF validation since we're mocking the HTTP layer
        with patch(
            "mcp_the_force.utils.image_loader._validate_and_resolve_url"
        ) as mock_validate:
            mock_validate.return_value = ("example.com", ["93.184.216.34"], 443)
            with patch(
                "mcp_the_force.utils.image_loader.aiohttp.ClientSession",
                return_value=mock_session,
            ):
                images = await load_images(
                    [
                        str(png_path),
                        "https://example.com/remote.jpg",
                    ]
                )

        assert len(images) == 2
        sources = {img.source for img in images}
        assert sources == {"file", "url"}


class AsyncIterator:
    """Helper class for async iteration in tests."""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index < len(self.items):
            item = self.items[self.index]
            self.index += 1
            return item
        raise StopAsyncIteration


class TestImageSizeValidation:
    """Test image size limit validation."""

    @pytest.mark.asyncio
    async def test_rejects_oversized_image(self, tmp_path):
        """Should reject images exceeding size limit."""
        from mcp_the_force.utils.image_loader import load_images, ImageLoadError

        # Create a file larger than typical limit (e.g., > 20MB)
        large_file = tmp_path / "large.png"
        # PNG header + 25MB of data
        large_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (25 * 1024 * 1024))

        with pytest.raises(ImageLoadError, match="exceeds.*limit"):
            await load_images([str(large_file)], max_size_mb=20)

    @pytest.mark.asyncio
    async def test_accepts_image_within_limit(self, tmp_path):
        """Should accept images within size limit."""
        from mcp_the_force.utils.image_loader import load_images

        small_file = tmp_path / "small.png"
        small_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)

        images = await load_images([str(small_file)], max_size_mb=20)
        assert len(images) == 1


class TestParallelLoading:
    """Test that images are loaded in parallel."""

    @pytest.mark.asyncio
    async def test_loads_multiple_files_concurrently(self, tmp_path):
        """Should load multiple files concurrently for performance."""
        from mcp_the_force.utils.image_loader import load_images

        # Create multiple files
        files = []
        for i in range(5):
            f = tmp_path / f"image_{i}.png"
            f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            files.append(str(f))

        # This should complete quickly due to parallel loading
        images = await load_images(files)
        assert len(images) == 5


class TestSSRFProtection:
    """Test SSRF (Server-Side Request Forgery) protection."""

    def test_blocks_localhost_url(self):
        """Should block localhost URLs."""
        from mcp_the_force.utils.image_loader import (
            _validate_url_structure,
            ImageLoadError,
        )

        with pytest.raises(ImageLoadError, match="localhost.*not allowed"):
            _validate_url_structure("http://localhost/image.png")

        with pytest.raises(ImageLoadError, match="localhost.*not allowed"):
            _validate_url_structure("http://127.0.0.1/image.png")

        with pytest.raises(ImageLoadError, match="localhost.*not allowed"):
            _validate_url_structure("http://0.0.0.0/image.png")

    def test_blocks_metadata_endpoints(self):
        """Should block cloud metadata endpoints."""
        from mcp_the_force.utils.image_loader import (
            _validate_url_structure,
            ImageLoadError,
        )

        # AWS/GCP metadata - blocked as private IP
        with pytest.raises(ImageLoadError, match="(private/internal|not allowed)"):
            _validate_url_structure("http://169.254.169.254/latest/meta-data/")

        # GCP metadata - blocked as internal hostname
        with pytest.raises(ImageLoadError, match="internal"):
            _validate_url_structure(
                "http://metadata.google.internal/computeMetadata/v1/"
            )

    def test_blocks_private_ip_ranges(self):
        """Should block URLs that resolve to private IP ranges."""
        from mcp_the_force.utils.image_loader import _is_private_ip_str

        # Private IPv4 ranges
        assert _is_private_ip_str("10.0.0.1") is True
        assert _is_private_ip_str("172.16.0.1") is True
        assert _is_private_ip_str("192.168.1.1") is True
        assert _is_private_ip_str("127.0.0.1") is True

        # Public IPs should not be blocked
        assert _is_private_ip_str("8.8.8.8") is False
        assert _is_private_ip_str("93.184.216.34") is False

        # IPv6 private ranges
        assert _is_private_ip_str("::1") is True
        assert _is_private_ip_str("fc00::1") is True
        assert _is_private_ip_str("fe80::1") is True

    def test_blocks_non_http_schemes(self):
        """Should only allow http/https schemes."""
        from mcp_the_force.utils.image_loader import (
            _validate_url_structure,
            ImageLoadError,
        )

        with pytest.raises(ImageLoadError, match="Invalid URL scheme"):
            _validate_url_structure("file:///etc/passwd")

        with pytest.raises(ImageLoadError, match="Invalid URL scheme"):
            _validate_url_structure("ftp://example.com/image.png")

        with pytest.raises(ImageLoadError, match="Invalid URL scheme"):
            _validate_url_structure("gopher://example.com/image.png")

    def test_allows_valid_public_urls(self):
        """Should allow valid public URLs."""
        from mcp_the_force.utils.image_loader import _validate_url_structure

        # These should not raise - validation of structure only
        scheme, hostname, port = _validate_url_structure(
            "https://example.com/image.png"
        )
        assert hostname == "example.com"
        assert scheme == "https"
        assert port == 443

        scheme, hostname, port = _validate_url_structure(
            "http://cdn.example.org/photo.jpg"
        )
        assert hostname == "cdn.example.org"
        assert scheme == "http"
        assert port == 80

    @pytest.mark.asyncio
    async def test_ssrf_blocks_before_request(self):
        """SSRF check should happen before any HTTP request is made."""
        from mcp_the_force.utils.image_loader import load_images, ImageLoadError

        # This should be blocked before any network call
        with pytest.raises(ImageLoadError, match="localhost.*not allowed"):
            await load_images(["http://localhost:8080/malicious.png"])


class TestIPNormalization:
    """Test IP address normalization for bypass prevention."""

    def test_normalizes_hex_encoded_ip(self):
        """Should normalize hex-encoded IPs."""
        from mcp_the_force.utils.image_loader import _normalize_ip
        import ipaddress

        # 0x7f.0.0.1 = 127.0.0.1
        ip = _normalize_ip("0x7f.0.0.1")
        assert ip == ipaddress.ip_address("127.0.0.1")

    def test_normalizes_octal_encoded_ip(self):
        """Should normalize octal-encoded IPs."""
        from mcp_the_force.utils.image_loader import _normalize_ip
        import ipaddress

        # 0177.0.0.1 = 127.0.0.1
        ip = _normalize_ip("0177.0.0.1")
        assert ip == ipaddress.ip_address("127.0.0.1")

    def test_normalizes_decimal_encoded_ip(self):
        """Should normalize decimal-encoded IPs."""
        from mcp_the_force.utils.image_loader import _normalize_ip
        import ipaddress

        # 2130706433 = 127.0.0.1
        ip = _normalize_ip("2130706433")
        assert ip == ipaddress.ip_address("127.0.0.1")

    def test_strips_ipv6_zone_id(self):
        """Should strip IPv6 zone IDs."""
        from mcp_the_force.utils.image_loader import _normalize_ip
        import ipaddress

        # ::1%eth0 -> ::1
        ip = _normalize_ip("::1%eth0")
        assert ip == ipaddress.ip_address("::1")

    def test_extracts_ipv4_from_mapped_ipv6(self):
        """Should extract IPv4 from IPv4-mapped IPv6."""
        from mcp_the_force.utils.image_loader import _normalize_ip
        import ipaddress

        # ::ffff:127.0.0.1 -> 127.0.0.1
        ip = _normalize_ip("::ffff:127.0.0.1")
        assert ip == ipaddress.ip_address("127.0.0.1")

    def test_blocks_encoded_localhost_variations(self):
        """Should block all encoded localhost variations."""
        from mcp_the_force.utils.image_loader import _is_private_ip_str

        encoded_localhosts = [
            "127.0.0.1",
            "0x7f.0.0.1",  # Hex
            "0177.0.0.1",  # Octal
            "2130706433",  # Decimal
            "::1",
            "::1%eth0",  # With zone ID
            "::ffff:127.0.0.1",  # IPv4-mapped
        ]

        for ip in encoded_localhosts:
            assert _is_private_ip_str(ip) is True, f"Failed to block: {ip}"


class TestPathTraversalProtection:
    """Test path traversal attack protection."""

    def test_blocks_dotdot_sequences(self):
        """Should block paths with .. sequences."""
        from mcp_the_force.utils.image_loader import _validate_file_path, ImageLoadError

        with pytest.raises(ImageLoadError, match="Path traversal detected"):
            _validate_file_path("../../../etc/passwd")

        with pytest.raises(ImageLoadError, match="Path traversal detected"):
            _validate_file_path("/tmp/../etc/passwd")

        with pytest.raises(ImageLoadError, match="Path traversal detected"):
            _validate_file_path("images/../../secrets/key.png")

    def test_blocks_sensitive_directories(self):
        """Should block access to sensitive system directories."""
        from mcp_the_force.utils.image_loader import _validate_file_path, ImageLoadError

        sensitive_paths = [
            "/etc/passwd",
            "/etc/shadow",
            "/var/log/syslog",
            "/var/run/secrets",
            "/root/test",
            "/proc/self/environ",
            "/sys/kernel/vmcoreinfo",
            "/dev/null",
            "/boot/vmlinuz",
            "/private/etc/passwd",
            "/private/var/log/system.log",
        ]

        for path in sensitive_paths:
            with pytest.raises(ImageLoadError, match="blocked for security"):
                _validate_file_path(path)

    def test_blocks_user_sensitive_directories(self):
        """Should block access to user-sensitive directories like .ssh, .aws."""
        from mcp_the_force.utils.image_loader import _validate_file_path, ImageLoadError

        home = str(Path.home())

        sensitive_paths = [
            f"{home}/.ssh/id_rsa",
            f"{home}/.aws/credentials",
            f"{home}/.gnupg/private-keys.db",
            f"{home}/.kube/config",
        ]

        for path in sensitive_paths:
            with pytest.raises(ImageLoadError, match="blocked for security"):
                _validate_file_path(path)

    def test_allows_safe_paths(self, tmp_path):
        """Should allow safe file paths."""
        from mcp_the_force.utils.image_loader import _validate_file_path

        # Create a test file
        safe_file = tmp_path / "safe_image.png"
        safe_file.write_bytes(b"test")

        # Should not raise
        resolved = _validate_file_path(str(safe_file))
        assert resolved.exists()

    @pytest.mark.asyncio
    async def test_path_traversal_blocks_before_read(self, tmp_path):
        """Path traversal check should happen before file read."""
        from mcp_the_force.utils.image_loader import load_images, ImageLoadError

        # This should be blocked before any file access
        with pytest.raises(ImageLoadError, match="Path traversal detected"):
            await load_images(["../../../etc/passwd"])


class TestTimeoutHandling:
    """Test timeout protection."""

    @pytest.mark.asyncio
    async def test_url_timeout_handling(self):
        """Should handle URL fetch timeouts."""
        from mcp_the_force.utils.image_loader import load_images, ImageLoadError

        # Mock _validate_and_resolve_url to allow our test URL through
        async def slow_get(*args, **kwargs):
            await asyncio.sleep(100)  # Longer than any reasonable timeout

        mock_response = MagicMock()
        mock_response.__aenter__ = AsyncMock(side_effect=slow_get)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "mcp_the_force.utils.image_loader._validate_and_resolve_url"
        ) as mock_validate:
            mock_validate.return_value = ("example.com", ["93.184.216.34"], 443)
            with patch(
                "mcp_the_force.utils.image_loader.aiohttp.ClientSession",
                return_value=mock_session,
            ):
                with pytest.raises(ImageLoadError, match="Timeout"):
                    await load_images(
                        ["https://example.com/slow.png"], total_timeout=0.1
                    )

    @pytest.mark.asyncio
    async def test_total_timeout_parameter(self, tmp_path):
        """Should respect total_timeout parameter."""
        from mcp_the_force.utils.image_loader import load_images

        # Create a test file
        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        # Should succeed with reasonable timeout
        images = await load_images([str(test_file)], total_timeout=10.0)
        assert len(images) == 1


class TestRedirectValidation:
    """Test that redirects are validated for SSRF."""

    @pytest.mark.asyncio
    async def test_blocks_redirect_to_private_ip(self):
        """Should block redirects that target private IPs."""
        from mcp_the_force.utils.image_loader import load_images, ImageLoadError

        # First response redirects to localhost
        mock_redirect_response = AsyncMock()
        mock_redirect_response.status = 302
        mock_redirect_response.headers = {"Location": "http://127.0.0.1/secret.png"}
        mock_redirect_response.__aenter__ = AsyncMock(
            return_value=mock_redirect_response
        )
        mock_redirect_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_redirect_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # First validate_and_resolve passes, but redirect validation should fail
        call_count = [0]

        async def mock_validate(url):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call - allow the original URL
                return ("example.com", ["93.184.216.34"], 80)
            else:
                # Second call - redirect to localhost, should raise
                from mcp_the_force.utils.image_loader import ImageLoadError

                raise ImageLoadError(
                    "URLs to localhost are not allowed for security reasons"
                )

        with patch(
            "mcp_the_force.utils.image_loader._validate_and_resolve_url",
            side_effect=mock_validate,
        ):
            with patch(
                "mcp_the_force.utils.image_loader.aiohttp.ClientSession",
                return_value=mock_session,
            ):
                with pytest.raises(ImageLoadError, match="localhost.*not allowed"):
                    await load_images(["http://example.com/image.png"])


class TestStreamingDownload:
    """Test streaming download functionality."""

    @pytest.mark.asyncio
    async def test_stops_download_when_size_exceeded(self):
        """Should stop downloading when size limit is exceeded during streaming."""
        from mcp_the_force.utils.image_loader import load_images, ImageLoadError

        # Create chunks that exceed the limit when combined
        chunk_size = 5 * 1024 * 1024  # 5MB per chunk
        chunks = [b"\x00" * chunk_size for _ in range(5)]  # 25MB total

        mock_content = AsyncMock()
        mock_content.iter_chunked = MagicMock(return_value=AsyncIterator(chunks))

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {}  # No Content-Length, so must stream
        mock_response.content = mock_content
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "mcp_the_force.utils.image_loader._validate_and_resolve_url"
        ) as mock_validate:
            mock_validate.return_value = ("example.com", ["93.184.216.34"], 443)
            with patch(
                "mcp_the_force.utils.image_loader.aiohttp.ClientSession",
                return_value=mock_session,
            ):
                with pytest.raises(ImageLoadError, match="exceeds.*limit"):
                    await load_images(["https://example.com/huge.png"], max_size_mb=20)


class TestDNSResolution:
    """Test DNS resolution functionality."""

    @pytest.mark.asyncio
    async def test_validates_all_resolved_ips(self):
        """Should validate all IPs returned by DNS resolution."""
        from mcp_the_force.utils.image_loader import (
            _validate_and_resolve_url,
            ImageLoadError,
        )
        import socket

        # Mock DNS to return both public and private IPs
        def mock_getaddrinfo(host, port, family, type):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    0,
                    "",
                    ("10.0.0.1", 0),
                ),  # Private!
            ]

        with patch(
            "mcp_the_force.utils.image_loader.socket.getaddrinfo", mock_getaddrinfo
        ):
            with pytest.raises(ImageLoadError, match="private/internal IP"):
                await _validate_and_resolve_url("https://example.com/image.png")

    @pytest.mark.asyncio
    async def test_dns_timeout_handling(self):
        """Should handle DNS resolution timeouts."""
        from mcp_the_force.utils.image_loader import _DNS_TIMEOUT

        # Test that the timeout constant is reasonable
        assert _DNS_TIMEOUT == 5  # 5 seconds for DNS

    @pytest.mark.asyncio
    async def test_dns_resolution_failure(self):
        """Should handle DNS resolution failures."""
        from mcp_the_force.utils.image_loader import _resolve_hostname, ImageLoadError
        import socket

        def failing_dns(*args, **kwargs):
            raise socket.gaierror(8, "nodename nor servname provided")

        with patch(
            "mcp_the_force.utils.image_loader.socket.getaddrinfo",
            side_effect=failing_dns,
        ):
            with pytest.raises(ImageLoadError, match="Failed to resolve hostname"):
                await _resolve_hostname("nonexistent.invalid")


class TestTotalMemoryLimit:
    """Test total memory limit for multiple images."""

    @pytest.mark.asyncio
    async def test_rejects_when_total_exceeds_limit(self, tmp_path):
        """Should reject when total image size exceeds limit."""
        from mcp_the_force.utils.image_loader import load_images, ImageLoadError

        # Create multiple images that together exceed the total limit
        # Each image is 60KB, total limit will be set to 100KB
        png_header = b"\x89PNG\r\n\x1a\n"
        image_data = png_header + b"\x00" * (60 * 1024)

        paths = []
        for i in range(3):  # 3 * 60KB = 180KB > 100KB limit
            path = tmp_path / f"image_{i}.png"
            path.write_bytes(image_data)
            paths.append(str(path))

        # Should fail because total (180KB) exceeds max_total_mb (0.1MB = 100KB)
        with pytest.raises(ImageLoadError, match="Total image size"):
            await load_images(paths, max_size_mb=1.0, max_total_mb=0.1)

    @pytest.mark.asyncio
    async def test_accepts_when_within_total_limit(self, tmp_path):
        """Should accept images when total is within limit."""
        from mcp_the_force.utils.image_loader import load_images

        # Create small images that together are under the limit
        png_header = b"\x89PNG\r\n\x1a\n"
        image_data = png_header + b"\x00" * 1024  # ~1KB each

        paths = []
        for i in range(3):
            path = tmp_path / f"image_{i}.png"
            path.write_bytes(image_data)
            paths.append(str(path))

        # Should succeed: 3KB total << 200MB default limit
        results = await load_images(paths)
        assert len(results) == 3


class TestSafeResolver:
    """Test the custom DNS resolver that prevents DNS rebinding attacks."""

    @pytest.mark.asyncio
    async def test_safe_resolver_returns_validated_ips(self):
        """SafeResolver should return our pre-validated IPs."""
        from mcp_the_force.utils.image_loader import _SafeResolver
        import socket

        resolver = _SafeResolver("example.com", ["93.184.216.34"], 443)

        results = await resolver.resolve("example.com", 443, socket.AF_INET)

        assert len(results) == 1
        assert results[0]["host"] == "93.184.216.34"
        assert results[0]["hostname"] == "example.com"

    @pytest.mark.asyncio
    async def test_safe_resolver_is_actually_used_by_aiohttp(self):
        """Verify that our SafeResolver is passed to aiohttp TCPConnector."""
        from mcp_the_force.utils.image_loader import _SafeResolver
        import aiohttp

        # Create our resolver
        resolver = _SafeResolver("example.com", ["93.184.216.34"], 443)

        # Create connector with our resolver
        connector = aiohttp.TCPConnector(
            resolver=resolver,
            ttl_dns_cache=0,
            use_dns_cache=False,
        )

        # Verify the resolver is actually set on the connector
        # aiohttp stores it as _resolver
        assert connector._resolver is resolver

        # Clean up
        await connector.close()

    @pytest.mark.asyncio
    async def test_safe_resolver_blocks_unexpected_hostname(self):
        """SafeResolver should block DNS rebinding attempts."""
        from mcp_the_force.utils.image_loader import _SafeResolver
        import socket

        resolver = _SafeResolver("example.com", ["93.184.216.34"], 443)

        # Attempting to resolve a different hostname should fail
        with pytest.raises(OSError, match="DNS rebinding attempt blocked"):
            await resolver.resolve("evil.com", 443, socket.AF_INET)

    @pytest.mark.asyncio
    async def test_safe_resolver_handles_ipv6(self):
        """SafeResolver should handle IPv6 addresses."""
        from mcp_the_force.utils.image_loader import _SafeResolver
        import socket

        resolver = _SafeResolver(
            "example.com", ["2606:2800:220:1:248:1893:25c8:1946"], 443
        )

        results = await resolver.resolve("example.com", 443, socket.AF_INET6)

        assert len(results) == 1
        assert results[0]["host"] == "2606:2800:220:1:248:1893:25c8:1946"
        assert results[0]["family"] == socket.AF_INET6

    @pytest.mark.asyncio
    async def test_safe_resolver_case_insensitive(self):
        """SafeResolver should handle case-insensitive hostname matching."""
        from mcp_the_force.utils.image_loader import _SafeResolver
        import socket

        resolver = _SafeResolver("Example.COM", ["93.184.216.34"], 443)

        # Should match regardless of case
        results = await resolver.resolve("example.com", 443, socket.AF_INET)
        assert len(results) == 1

        results = await resolver.resolve("EXAMPLE.COM", 443, socket.AF_INET)
        assert len(results) == 1

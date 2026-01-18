# Image Input Support Plan

## Overview

Add the ability to pass images to vision-capable models (Gemini, Claude, GPT-4o/GPT-5) through The Force MCP tools.

## Research Summary

### Provider API Formats

| Provider | Format | Max Size | Max Images |
|----------|--------|----------|------------|
| **OpenAI** | `{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}` | 20MB | 10/request |
| **Gemini** | `{"inline_data": {"mime_type": "image/jpeg", "data": "..."}}` | 100MB | No strict limit |
| **Claude** | `{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "..."}}` | 3.75MB | 20/request |

### Supported MIME Types
- All providers: `image/jpeg`, `image/png`, `image/gif`, `image/webp`

## Implementation Plan

### Phase 1: Core Infrastructure

#### 1.1 Add `images` Parameter to Tool Definitions

Add a new parameter to `BaseToolParams` in `mcp_the_force/tools/base.py`:

```python
images: List[str] = Route.prompt(
    default=[],
    description=(
        "(Optional) List of image paths or URLs to include in the request. "
        "Supports local file paths (absolute) and HTTP/HTTPS URLs. "
        "Images are sent to the model for visual analysis. "
        "Syntax: An array of strings. "
        "Example: ['/path/to/image.png', 'https://example.com/photo.jpg']"
    ),
    requires_capability=lambda c: c.supports_vision,
)
```

#### 1.2 Create Image Processing Utility

New file: `mcp_the_force/utils/image_loader.py`

```python
@dataclass
class LoadedImage:
    data: bytes
    mime_type: str
    source: str  # 'file' or 'url'
    original_path: str

async def load_images(paths: List[str]) -> List[LoadedImage]:
    """Load images from file paths or URLs."""
    # - Detect if path is URL or file
    # - Load content (aiohttp for URLs, aiofiles for local)
    # - Detect MIME type from content or extension
    # - Validate size limits
    # - Return structured LoadedImage objects
```

#### 1.3 Create Provider-Specific Formatters

New file: `mcp_the_force/utils/image_formatter.py`

```python
def format_for_openai(images: List[LoadedImage]) -> List[dict]:
    """Format images for OpenAI API."""
    return [{
        "type": "image_url",
        "image_url": {
            "url": f"data:{img.mime_type};base64,{base64.b64encode(img.data).decode()}"
        }
    } for img in images]

def format_for_gemini(images: List[LoadedImage]) -> List[dict]:
    """Format images for Gemini API."""
    return [{
        "inline_data": {
            "mime_type": img.mime_type,
            "data": base64.b64encode(img.data).decode()
        }
    } for img in images]

def format_for_anthropic(images: List[LoadedImage]) -> List[dict]:
    """Format images for Anthropic API."""
    return [{
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": img.mime_type,
            "data": base64.b64encode(img.data).decode()
        }
    } for img in images]
```

### Phase 2: Adapter Integration

#### 2.1 Update OpenAI Adapter

Modify `mcp_the_force/adapters/openai/adapter.py`:
- Accept images in `generate()` method
- Build multimodal content array: `[{"type": "text", "text": prompt}, ...image_parts]`
- Pass to Responses API

#### 2.2 Update Gemini Adapter

Modify `mcp_the_force/adapters/google/adapter.py`:
- Accept images in `generate()` method
- Build content parts: `[types.Part.from_text(prompt), *image_parts]`
- Use `types.Part.from_bytes()` for images

#### 2.3 Update Anthropic Adapter

Modify `mcp_the_force/adapters/anthropic/adapter.py`:
- Accept images in `generate()` method
- Build content array with text and image blocks
- Pass to Messages API

### Phase 3: Tool Executor Integration

#### 3.1 Update Tool Executor

Modify `mcp_the_force/tools/executor.py`:
- Extract `images` parameter before calling adapter
- Load images using `load_images()`
- Pass loaded images to adapter's `generate()` method

### Phase 4: Capability Enforcement

#### 4.1 Update Capability Validator

Modify `mcp_the_force/tools/capability_validator.py`:
- Check `supports_vision` capability when images are provided
- Return clear error if model doesn't support vision

#### 4.2 Update Model Capabilities

Ensure correct `supports_vision` flags:
- `OpenAIBaseCapabilities`: `supports_vision = True` (for GPT-4o, GPT-5)
- `GeminiBaseCapabilities`: `supports_vision = True` ✓
- `AnthropicBaseCapabilities`: `supports_vision = True` ✓
- `GrokCapabilities`: `supports_vision = False` ✓

### Phase 5: Testing

#### 5.1 Unit Tests
- `test_image_loader.py`: Test file/URL loading, MIME detection, size validation
- `test_image_formatter.py`: Test provider-specific formatting
- `test_capability_validation.py`: Test vision capability enforcement

#### 5.2 Integration Tests
- Test image parameter flows through tool execution
- Mock adapter responses with image content

#### 5.3 E2E Tests (Optional)
- Real API calls with test images
- Verify each provider handles images correctly

## File Changes Summary

| File | Change |
|------|--------|
| `mcp_the_force/tools/base.py` | Add `images` parameter |
| `mcp_the_force/utils/image_loader.py` | **NEW** - Image loading utility |
| `mcp_the_force/utils/image_formatter.py` | **NEW** - Provider formatters |
| `mcp_the_force/adapters/openai/adapter.py` | Handle images in generate() |
| `mcp_the_force/adapters/google/adapter.py` | Handle images in generate() |
| `mcp_the_force/adapters/anthropic/adapter.py` | Handle images in generate() |
| `mcp_the_force/tools/executor.py` | Load and pass images |
| `mcp_the_force/tools/capability_validator.py` | Validate vision capability |
| `mcp_the_force/adapters/openai/definitions.py` | Set `supports_vision = True` |

## Considerations

### Security
- Validate file paths are within allowed directories
- Sanitize URLs to prevent SSRF
- Respect existing `SecurityConfig.path_blacklist`

### Performance
- Load images in parallel with `asyncio.gather()`
- Cache loaded images for multi-turn conversations?
- Consider lazy loading for large image sets

### Error Handling
- Clear errors for unsupported formats
- File not found / URL unreachable
- Size limit exceeded
- Model doesn't support vision

### Future Enhancements
- Support for image URLs directly (skip download for OpenAI/Claude)
- Image compression/resizing for size limits
- PDF support (Gemini supports it)
- Video frame extraction

## Sources

- [OpenAI Vision Docs](https://platform.openai.com/docs/guides/images-vision)
- [Gemini Image Understanding](https://ai.google.dev/gemini-api/docs/image-understanding)
- [Claude Vision Docs](https://docs.claude.com/en/docs/build-with-claude/vision)

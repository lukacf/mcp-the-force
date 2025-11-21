# Future Streaming Implementation

This document outlines the plan for implementing full client streaming support in MCP The-Force, based on research conducted with o3.

## Overview

Currently, MCP The-Force buffers complete AI model responses before returning them to clients. With streaming support, clients would see responses appear word-by-word in real-time, significantly improving perceived latency for long responses.

## Key Discovery: FastMCP Already Supports Streaming

FastMCP 2.3+ has built-in streaming support that we can leverage:
- Tools can be annotated with `@mcp.tool(annotations={"streamingHint": True})`
- Context object provides `ctx.stream_text(chunk)` for sending incremental updates
- Both stdio and HTTP transports handle streaming properly
- Claude Code already renders streamed chunks

## Current Streaming Support Status

### Models with Streaming Capability
- ✅ **Already streaming internally**: o3, o4-mini, gpt-4.1 (OpenAI models)
- 🚫 **Intentionally non-streaming**: o3-pro (background-only due to long processing times)
- ⚠️ **Could stream but don't**: Gemini 3 Pro Preview/Flash, Grok 3 Beta/4

## Implementation Plan

### Phase 1: Internal Streaming (Optional Quick Win)
**Complexity**: 2/5 | **Timeline**: 3-4 days

Make Gemini and Grok models stream internally (to reduce latency) while still returning complete responses:
- Add `stream=True` to LiteLLM request parameters
- Collect chunks internally and return final content
- No protocol changes required

### Phase 2: Full Client Streaming (Recommended)
**Complexity**: 2/5 | **Timeline**: 3 days

#### Day 1: OpenAI Adapter
Extract existing streaming logic into a generator:
```python
class OpenAIAdapter:
    async def generate_stream(self, ...) -> AsyncIterator[str]:
        async for event in stream:
            if event.type == "response.delta":
                yield event.delta
    
    # Backward compatibility
    async def generate(self, ...):
        return "".join([chunk async for chunk in self.generate_stream(...)])
```

#### Day 2: Gemini/Grok Adapters
Add streaming support to LiteLLM-based adapters:
```python
class LiteLLMBaseAdapter:
    async def generate_stream(self, ...):
        response = await litellm.aresponses(..., stream=True)
        async for chunk in response:
            if hasattr(chunk, 'delta'):
                yield chunk.delta
```

#### Day 3: Integration Layer
Update tool registration and executor:

```python
# In create_tool_function
@mcp.tool(
    name=tool_id,
    annotations={"streamingHint": capabilities.supports_streaming}
)
async def tool_fn(*args, ctx: Context = None, **kwargs):
    # FastMCP injects ctx when streaming is supported
    
    if ctx and hasattr(adapter, "generate_stream"):
        # Stream chunks to client
        async for chunk in adapter.generate_stream(...):
            await ctx.stream_text(chunk)
        # Memory storage still happens after streaming completes
    else:
        # Non-streaming fallback
        content = await adapter.generate(...)
        return {"content": content}
```

## Architecture Benefits

1. **Minimal Changes**: Leverages existing FastMCP streaming infrastructure
2. **Backward Compatible**: Non-streaming adapters continue to work
3. **Hybrid Approach**: Some models stream (o3, gpt-4.1) while others don't (o3-pro)
4. **Memory Decoupled**: Storage happens after streaming completes
5. **Transport Agnostic**: Works with both stdio and HTTP

## Special Considerations

### Structured Output
When `structured_output_schema` is provided, buffer the complete response:
```python
if structured_output_schema:
    # Can't validate partial JSON
    return await self.generate(...)  # Use non-streaming path
```

### Progress Tracking
Combine with the proposed progress tracking system:
- Heartbeat logs while waiting for first token
- Token count logs during streaming
- Completion logs after stream ends

### Models That Stay Non-Streaming
- o3-pro (uses background jobs)
- deep-research models (very long processing times)
- Any model with `supports_streaming=False`

## Testing Strategy

1. **Unit Tests**: Mock streaming responses for each adapter
2. **Integration Tests**: Verify FastMCP streaming with mock adapters
3. **E2E Tests**: Real API calls with streaming enabled
4. **Performance Tests**: Measure time-to-first-token improvements

## Configuration

Add streaming control to settings:
```yaml
streaming:
  enabled: true  # Global toggle
  chunk_delay_ms: 0  # Optional throttling
  models:
    # Per-model overrides
    o3-pro: false  # Force background mode
```

## Migration Path

1. Implement streaming adapters behind feature flag
2. Test with Claude Code in development
3. Gradually enable for each model
4. Make streaming default in next major version

## Future Enhancements

- **Smart Buffering**: Coalesce very small chunks to reduce overhead
- **Stream Interruption**: Allow users to cancel mid-stream
- **Partial Results**: Show intermediate results for long-running operations
- **Token Counting**: Real-time token usage during streaming

## Conclusion

With FastMCP's existing streaming support, implementing full client streaming is straightforward. The 3-day implementation would provide significant UX improvements with minimal architectural changes.
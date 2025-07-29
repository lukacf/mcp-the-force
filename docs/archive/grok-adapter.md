# Grok Adapter Implementation Plan

## Overview

This document outlines the plan to add xAI's Grok models (Grok 3 and Grok 4) as first-class citizens in MCP The-Force. The integration leverages Grok's OpenAI-compatible API, allowing us to reuse much of our existing infrastructure.

## Research Findings

### 1. Grok Python SDK

**Official SDK**: `xai-sdk` (available on PyPI)
- Installation: `pip install xai-sdk`
- OpenAI-compatible client library
- Supports standard OpenAI Python SDK patterns

**Authentication**:
- API Key: `XAI_API_KEY` environment variable
- Base URL: `https://api.x.ai/v1`
- Requires X Premium+ subscription for API access

### 2. Available Grok Models

| Model | Context Window | Use Case | Notes |
|-------|---------------|----------|-------|
| `grok-3` | 131,000 tokens | General purpose, coding, Q&A | Fast, balanced |
| `grok-3-reasoning` | 131,000 tokens | Complex reasoning tasks | Slower, more thorough |
| `grok-4` | 256,000 tokens | Advanced reasoning, large docs | Multi-agent reasoning |
| `grok-4-heavy` | 256,000 tokens | Maximum capability | If available via API |
| `grok-3-mini` | ~32,000 tokens | Quick responses | Lower quality, faster |

### 3. API Capabilities

**Supported Features**:
- ✅ Text generation/completion
- ✅ Function calling (OpenAI-compatible format)
- ✅ Streaming responses
- ✅ Chat/conversation format
- ✅ System messages
- ✅ Temperature control
- ✅ Real-time X (Twitter) data access

**API Compatibility**:
- Full OpenAI API v1 compatibility
- Same request/response formats
- Compatible with OpenAI Python SDK
- Function calling uses same JSON schema format

**Rate Limits** (tentative based on research):
- ~60 requests/minute
- Token-based pricing similar to OpenAI
- Specific limits depend on subscription tier

### 4. Key Advantages

1. **Massive Context Windows**: 131k-256k tokens vs typical 8k-128k
2. **Real-time Information**: Access to current X/Twitter data
3. **OpenAI Compatibility**: Drop-in replacement for many use cases
4. **Advanced Reasoning**: Grok 4's multi-agent reasoning capabilities

## Implementation Plan

### Phase 1: Core Infrastructure

#### 1.1 Dependencies
```toml
# pyproject.toml
dependencies = [
    # ... existing deps ...
    "xai-sdk>=0.1.0",  # or use openai>=1.62.0 directly
]
```

#### 1.2 Configuration Updates

**Add to `mcp_the_force/config.py`**:
```python
class Settings(BaseSettings):
    # ... existing fields ...
    xai: ProviderConfig = Field(default_factory=ProviderConfig)
```

**Legacy environment variable mapping**:
```python
legacy_mappings = {
    # ... existing mappings ...
    "XAI_API_KEY": ("xai", "api_key"),
}
```

**Example config.yaml**:
```yaml
providers:
  xai:
    enabled: true
```

**Example secrets.yaml**:
```yaml
providers:
  xai:
    api_key: xai-...
```

### Phase 2: Adapter Implementation

#### 2.1 GrokAdapter Class

Create `mcp_the_force/adapters/grok/adapter.py`:

```python
from typing import Optional, AsyncIterator, Any, Dict
import logging
from openai import AsyncOpenAI

from ..base import BaseAdapter, AdapterException
from ..errors import ErrorCategory
from ...config import get_settings

logger = logging.getLogger(__name__)

# Model capabilities
GROK_CAPABILITIES = {
    "grok-3": {
        "context_window": 131_000,
        "supports_functions": True,
        "supports_streaming": True,
    },
    "grok-3-reasoning": {
        "context_window": 131_000,
        "supports_functions": True,
        "supports_streaming": True,
    },
    "grok-4": {
        "context_window": 256_000,
        "supports_functions": True,
        "supports_streaming": True,
    },
    "grok-4-heavy": {
        "context_window": 256_000,
        "supports_functions": True,
        "supports_streaming": True,
    },
    "grok-3-mini": {
        "context_window": 32_000,
        "supports_functions": True,
        "supports_streaming": True,
    },
}

class GrokAdapter(BaseAdapter):
    """Adapter for xAI Grok models using OpenAI-compatible API."""
    
    def __init__(self):
        super().__init__()
        settings = get_settings()
        
        if not settings.xai.api_key:
            raise AdapterException(
                "XAI_API_KEY not configured",
                error_category=ErrorCategory.CONFIGURATION
            )
        
        self.client = AsyncOpenAI(
            api_key=settings.xai.api_key,
            base_url="https://api.x.ai/v1",
        )
        self._supported_models = set(GROK_CAPABILITIES.keys())
    
    async def generate(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> AsyncIterator[str] | str:
        """Generate a response using Grok models."""
        
        if model not in self._supported_models:
            raise AdapterException(
                f"Model {model} not supported. Choose from: {', '.join(self._supported_models)}",
                error_category=ErrorCategory.INVALID_REQUEST
            )
        
        try:
            # Build request parameters
            request_params = {
                "model": model,
                "messages": messages,
                "temperature": temperature or 1.0,
                "stream": stream,
            }
            
            # Add optional parameters
            if "max_tokens" in kwargs:
                request_params["max_tokens"] = kwargs["max_tokens"]
            
            # Handle function calling if provided
            if "functions" in kwargs:
                request_params["tools"] = [
                    {"type": "function", "function": func} 
                    for func in kwargs["functions"]
                ]
                if "function_call" in kwargs:
                    request_params["tool_choice"] = kwargs["function_call"]
            
            # Handle structured output if provided
            if "response_format" in kwargs:
                request_params["response_format"] = kwargs["response_format"]
            
            logger.info(f"Calling Grok {model} with {len(messages)} messages")
            
            if stream:
                return self._stream_response(request_params)
            else:
                response = await self.client.chat.completions.create(**request_params)
                return response.choices[0].message.content or ""
                
        except Exception as e:
            logger.error(f"Grok API error: {str(e)}")
            if "rate_limit" in str(e).lower():
                raise AdapterException(
                    "Rate limit exceeded. Please wait before retrying.",
                    error_category=ErrorCategory.RATE_LIMIT
                )
            elif "api_key" in str(e).lower() or "unauthorized" in str(e).lower():
                raise AdapterException(
                    "Invalid API key or unauthorized access",
                    error_category=ErrorCategory.AUTHENTICATION
                )
            else:
                raise AdapterException(
                    f"Grok API error: {str(e)}",
                    error_category=ErrorCategory.API_ERROR
                )
    
    async def _stream_response(self, request_params: Dict[str, Any]) -> AsyncIterator[str]:
        """Stream response from Grok API."""
        try:
            stream = await self.client.chat.completions.create(**request_params)
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
                # Handle function calls in streaming
                if chunk.choices and chunk.choices[0].delta.tool_calls:
                    # For now, we'll handle function calls in non-streaming mode
                    # This is a limitation we can improve later
                    logger.warning("Function calls in streaming mode not fully supported yet")
                    
        except Exception as e:
            logger.error(f"Streaming error: {str(e)}")
            raise AdapterException(
                f"Streaming failed: {str(e)}",
                error_category=ErrorCategory.API_ERROR
            )
```

### Phase 3: Integration

#### 3.1 Update Model Registry

In `mcp_the_force/adapters/model_registry.py`:

```python
from .grok import GROK_CAPABILITIES

def get_model_context_window(model: str) -> int:
    """Get context window size for a model."""
    
    # ... existing code ...
    
    # Grok models
    if model in GROK_CAPABILITIES:
        return GROK_CAPABILITIES[model]["context_window"]
    
    # Default fallback
    return 4096
```

#### 3.2 Update Adapter Factory

In `mcp_the_force/adapters/__init__.py`:

```python
def get_adapter(adapter_class: str, mock: bool = False) -> Tuple[BaseAdapter, Optional[str]]:
    """Get adapter instance by class name."""
    
    # ... existing code ...
    
    if adapter_class == "xai" or adapter_class == "grok":
        from .grok import GrokAdapter
        return GrokAdapter(), None
    
    # ... rest of code ...
```

#### 3.3 Create Tool Definitions

In `mcp_the_force/tools/definitions.py`:

```python
@tool
class ChatWithGrok3(ToolSpec):
    """General-purpose assistant using xAI Grok 3 model (131k context).
    Excels at: coding, Q&A, and real-time info via X data.
    
    Example usage:
    - instructions: "Summarize the latest AI news from X"
    - output_format: "Bullet points with links"
    - context: ["/project/docs/requirements.md"]
    - temperature: 0.3 (lower for consistency)
    - session_id: "grok-session-001" (for conversations)
    """
    model_name = "grok-3"
    adapter_class = "xai"
    context_window = 131_000
    timeout = 300
    
    instructions: str = Route.prompt(pos=0, description="User instructions or question")
    output_format: str = Route.prompt(pos=1, description="Desired output format or response style")
    context: List[str] = Route.prompt(pos=2, description="File paths or content to provide as context")
    session_id: str = Route.session(description="Session ID to link multi-turn conversations")
    attachments: Optional[List[str]] = Route.vector_store(description="Additional files for RAG")
    temperature: Optional[float] = Route.adapter(default=1.0, description="Sampling temperature (0-2)")
    structured_output_schema: Optional[Dict[str, Any]] = Route.structured_output(
        description="JSON Schema for structured output (optional)"
    )

@tool
class ChatWithGrok4(ToolSpec):
    """Advanced assistant using xAI Grok 4 model (256k context, multi-agent reasoning).
    Excels at: complex reasoning, code analysis, large documents.
    
    Example usage:
    - instructions: "Analyze this entire codebase and suggest refactoring"
    - output_format: "Detailed report with code examples"
    - context: ["/src"] (can handle massive contexts)
    - session_id: "grok4-analysis-001"
    """
    model_name = "grok-4"
    adapter_class = "xai"
    context_window = 256_000
    timeout = 600  # Longer timeout for complex reasoning
    
    instructions: str = Route.prompt(pos=0, description="User instructions")
    output_format: str = Route.prompt(pos=1, description="Format requirements for the answer")
    context: List[str] = Route.prompt(pos=2, description="Context file paths or snippets")
    session_id: str = Route.session(description="Session ID for multi-turn context")
    attachments: Optional[List[str]] = Route.vector_store(description="Files for vector database context")
    temperature: Optional[float] = Route.adapter(default=0.7, description="Sampling temperature (0-2)")
    structured_output_schema: Optional[Dict[str, Any]] = Route.structured_output(
        description="JSON Schema for structured output (optional)"
    )

@tool
class ChatWithGrok3Reasoning(ToolSpec):
    """Deep reasoning using xAI Grok 3 Reasoning model (131k context).
    Excels at: complex problem solving, mathematical reasoning, code debugging.
    Note: Slower than regular Grok 3 but more thorough.
    """
    model_name = "grok-3-reasoning"
    adapter_class = "xai"
    context_window = 131_000
    timeout = 900  # Longer timeout for reasoning mode
    
    instructions: str = Route.prompt(pos=0, description="Complex problem or question")
    output_format: str = Route.prompt(pos=1, description="Desired output structure")
    context: List[str] = Route.prompt(pos=2, description="Relevant context files")
    session_id: str = Route.session(description="Session ID for multi-step reasoning")
    attachments: Optional[List[str]] = Route.vector_store(description="Additional reference materials")
    temperature: Optional[float] = Route.adapter(default=0.3, description="Lower temp for consistent reasoning")
```

### Phase 4: Testing Plan

#### 4.1 Unit Tests

Create `tests/unit/test_grok_adapter.py`:
- Test adapter initialization with/without API key
- Test model validation
- Test error handling (rate limits, auth errors)
- Mock API responses for generate method

#### 4.2 Integration Tests

1. **Basic Completion Test**:
   ```python
   result = await mcp.call_tool(
       "chat_with_grok3",
       instructions="Hello, introduce yourself",
       output_format="Brief introduction",
       context=[]
   )
   ```

2. **Function Calling Test**:
   - Provide a calculation function
   - Ask Grok to solve a math problem
   - Verify function is called correctly

3. **Large Context Test**:
   - Load 100k+ tokens of text
   - Verify Grok can process it
   - Test with Grok 4 (256k context)

4. **Streaming Test**:
   - Generate long response
   - Verify streaming works properly
   - Check partial token delivery

#### 4.3 E2E Tests

Add Grok scenarios to `tests/e2e_dind/scenarios/`:
- Cross-model comparison (Grok vs GPT-4)
- Session continuity tests
- Vector store integration with large files

### Phase 5: Documentation Updates

#### 5.1 README.md Updates

Add to Available Tools section:
```markdown
### Grok Models (xAI)

| Tool | Model | Best For | Context |
|------|-------|----------|---------|
| `chat_with_grok3` | Grok 3 | General Q&A, coding, real-time X data | 131k tokens |
| `chat_with_grok3_reasoning` | Grok 3 Reasoning | Complex reasoning, debugging | 131k tokens |
| `chat_with_grok4` | Grok 4 | Advanced analysis, large documents | 256k tokens |
```

#### 5.2 Configuration Guide

Add Grok setup instructions:
```markdown
## Grok (xAI) Setup

1. Get your API key from [x.ai](https://x.ai) (requires X Premium+)
2. Add to your `secrets.yaml`:
   ```yaml
   providers:
     xai:
       api_key: xai-...
   ```
3. Or set environment variable: `XAI_API_KEY=xai-...`
```

### Phase 6: Advanced Features (Future)

1. **Grok-specific Parameters**:
   - Web search toggle (if available)
   - X data recency preferences
   - Reasoning depth control

2. **Model Variants**:
   - Add Grok 4 Heavy when available
   - Mini model for cost optimization

3. **Function Calling Enhancements**:
   - Parallel function execution
   - Streaming with function calls

## Migration Considerations

### For Existing Users

- No breaking changes
- Grok is opt-in via tool selection
- Existing workflows continue unchanged

### Performance Considerations

- Grok's large context may increase memory usage
- Consider token counting optimizations
- May need to adjust timeouts for reasoning models

## Security Considerations

1. **API Key Management**:
   - Store in secrets.yaml (gitignored)
   - Use environment variables in production
   - Never log API keys

2. **Rate Limiting**:
   - Implement exponential backoff
   - Track usage per session
   - Provide clear error messages

## Success Criteria

1. ✅ Grok models available as tools
2. ✅ Seamless integration with existing features
3. ✅ Proper error handling and messaging
4. ✅ Documentation and examples
5. ✅ All tests passing
6. ✅ Performance comparable to other adapters
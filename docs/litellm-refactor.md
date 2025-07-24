# LiteLLM Adapter Architecture Refactor

## Overview

This document outlines the architectural refactor to use LiteLLM as the underlying implementation for individual provider adapters in mcp-the-force. The goal is to eliminate provider-specific code scattered throughout the codebase while maintaining support for provider-specific features.

**Important**: We are NOT creating a single universal LiteLLM adapter. Instead, we're creating separate adapters (GrokAdapter, OpenAIAdapter, etc.) that each use LiteLLM internally for their implementation.

## Design Principles

1. **Adapter Isolation**: No provider-specific logic outside adapter classes
2. **Type Safety**: Use dataclasses and Python's type system 
3. **Unified Interfaces**: Leverage LiteLLM's unified message format
4. **Extensibility**: Easy to add new providers without modifying core framework

## Architecture Components

### 1. Adapter Protocol

All adapters must satisfy this protocol (duck typing, no inheritance required):

```python
from typing import Protocol, Any
from dataclasses import dataclass

class MCPAdapter(Protocol):
    """Interface that all adapters must satisfy"""
    capabilities: AdapterCapabilities
    param_class: type
    display_name: str
    
    async def generate(
        self,
        prompt: str,
        params: Any,  # Instance of param_class
        ctx: CallCtx,
        *,
        tool_dispatcher: ToolDispatcher
    ) -> dict:
        """Generate response from the model"""
        ...
```

### 2. Adapter Capabilities

Simple dataclass declaring what the adapter can do:

```python
@dataclass
class AdapterCapabilities:
    """What the framework needs to know about an adapter"""
    native_file_search: bool = False
    supports_functions: bool = True
    parallel_function_calls: Optional[int] = None
    max_context_window: Optional[int] = None
    # Add more capabilities as needed
```

### 3. Parameter Classes

Type-safe parameter definitions using existing Route descriptors:

```python
@dataclass
class BaseToolParams:
    """Parameters every tool has"""
    instructions: str = Route.prompt(pos=0)
    output_format: str = Route.prompt(pos=1) 
    context: List[str] = Route.prompt(pos=2)
    session_id: str = Route.session()

@dataclass
class GrokToolParams(BaseToolParams):
    """Grok-specific additions"""
    search_mode: Optional[str] = Route.adapter(default="auto")
    search_parameters: Optional[Dict[str, Any]] = Route.adapter()
    return_citations: Optional[bool] = Route.adapter(default=True)

@dataclass
class LiteLLMParams(BaseToolParams):
    """Universal LiteLLM parameters with passthrough"""
    temperature: float = Route.adapter(default=0.7)
    extras: Dict[str, Any] = Route.adapter(
        default_factory=dict,
        description="Provider-specific parameters"
    )
```

### 4. Unified Session Cache

Single cache using LiteLLM's message format for all providers:

```python
class UnifiedSessionCache:
    """Adapter-agnostic conversation storage"""
    
    async def save(
        self, 
        session_id: str, 
        messages: List[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Save conversation in LiteLLM format"""
        await self.db.save(session_id, {
            "messages": messages,
            "metadata": metadata or {}
        })
    
    async def load(self, session_id: str) -> Dict[str, Any]:
        """Load conversation in LiteLLM format"""
        return await self.db.load(session_id) or {"messages": [], "metadata": {}}
```

### 5. Example: Grok Adapter Using LiteLLM

Each provider gets its own adapter that uses LiteLLM internally:

```python
class GrokLiteLLMAdapter(BaseAdapter):
    """Grok adapter using LiteLLM internally"""
    
    def __init__(self, model: str):
        self.model_name = model  # e.g., "grok-4"
        self.display_name = f"Grok {model} (via LiteLLM)"
        self.param_class = GrokToolParams
        self.capabilities = AdapterCapabilities(
            native_file_search=False,
            supports_functions=True,
            supports_live_search=True
        )
        
        # Self-contained auth
        settings = get_settings()
        self.api_key = settings.xai_api_key
    
    def _build_capabilities(self) -> AdapterCapabilities:
        """Dynamic capabilities based on model"""
        # Get info from LiteLLM if available
        info = litellm.model_info.get(self.model_name, {})
        
        return AdapterCapabilities(
            native_file_search=(self.provider == "openai"),
            supports_functions=info.get("supports_functions", True),
            parallel_function_calls=info.get("parallel_tool_calls"),
            max_context_window=info.get("max_tokens", 128000)
        )
    
    async def generate(
        self,
        prompt: str,
        params: LiteLLMParams,
        ctx: CallCtx,
        *,
        tool_dispatcher: ToolDispatcher
    ) -> dict:
        """Generate using LiteLLM's unified interface"""
        # Load session
        session_data = await self.session_cache.load(ctx.session_id)
        messages = session_data["messages"]
        messages.append({"role": "user", "content": prompt})
        
        # Build request for LiteLLM
        request_params = {
            "model": f"grok/{self.model_name}",  # LiteLLM needs provider prefix
            "messages": messages,
            "temperature": params.temperature,
            "api_key": self.api_key,
            "api_base": "https://api.x.ai/v1",
            # Grok-specific params
            "extra_body": {
                "search_mode": params.search_mode,
                "search_parameters": params.search_parameters
            }
        }
        
        # Add tools if needed
        if ctx.vector_store_ids and not self.capabilities.native_file_search:
            # Tool dispatcher provides the declarations
            tools = tool_dispatcher.get_tool_declarations()
            request_params["tools"] = tools
        
        # Make request
        response = await litellm.acompletion(**request_params)
        
        # Handle tool calls if present
        while hasattr(response, "tool_calls") and response.tool_calls:
            # Execute tools
            tool_results = []
            for tool_call in response.tool_calls:
                result = await tool_dispatcher.execute(
                    tool_call.function.name,
                    tool_call.function.arguments,
                    ctx
                )
                tool_results.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "content": str(result)
                })
            
            # Continue conversation
            messages.extend(tool_results)
            request_params["messages"] = messages
            response = await litellm.acompletion(**request_params)
        
        # Save updated conversation
        messages.append({
            "role": "assistant",
            "content": response.choices[0].message.content
        })
        await self.session_cache.save(ctx.session_id, messages)
        
        return {
            "content": response.choices[0].message.content,
            "usage": response.usage.dict() if response.usage else {}
        }
```

## Authentication Configuration

### Design Principle: Self-Contained Auth

Each adapter is responsible for obtaining its own authentication credentials. No centralized auth resolver or provider-specific logic should exist outside adapters.

### Implementation

```python
class LiteLLMAdapter:
    def __init__(self, model: str):
        # Extract provider from model string
        self.provider = model.split("/")[0]  # "openai/gpt-4" -> "openai"
        
        # Get auth config for this provider
        settings = get_settings()
        self.auth_config = getattr(settings.providers, self.provider, {})
        # auth_config might be {"api_key": "sk-..."} or {} if using env vars
```

### Configuration Sources

1. **Development Mode** (current):
   - `config.yaml` / `secrets.yaml` files
   - Loaded into settings object
   - Convenient for developers

2. **Production Mode** (future):
   - MCP protocol configuration
   - Standard for end users
   - No yaml files needed

3. **Fallback**:
   - If auth_config is empty, LiteLLM checks environment variables
   - Supports both YAML config and pure env var deployments

### Why This Works

- **Maintains isolation**: Only the adapter knows about provider names
- **Flexible**: Supports YAML, env vars, and future MCP config
- **Simple**: No complex AuthResolver pattern
- **Testable**: Easy to inject test credentials

### Edge Cases

- **Missing credentials**: LiteLLM will raise clear errors
- **Multiple accounts**: Can extend to support profiles in settings
- **Key rotation**: Can refresh settings at runtime

## Migration Strategy

### Phase 1: Foundation (Day 1)
1. Create `AdapterCapabilities` dataclass
2. Create `UnifiedSessionCache` implementation
3. Define `MCPAdapter` protocol
4. Create base `LiteLLMAdapter` class

### Phase 2: Provider Migration (Day 2-3)
1. Migrate Grok adapter to use LiteLLM
2. Update tool definitions to use dynamic param classes
3. Remove provider-specific session caches
4. Update executor to use protocol

### Phase 3: Cleanup (Day 4)
1. Remove scattered `if adapter == "xai"` checks
2. Remove old adapter implementations (keep as fallback)
3. Update tests
4. Documentation

## Implementation Checklist

- [ ] Create `mcp_the_force/adapters/capabilities.py`
- [ ] Create `mcp_the_force/session_cache.py` (unified)
- [ ] Update `mcp_the_force/adapters/litellm/adapter.py`
- [ ] Add Grok support to LiteLLM adapter
- [ ] Implement self-contained auth in LiteLLM adapter
- [ ] Create provider-specific param classes
- [ ] Update executor to pass validated param instances
- [ ] Remove provider-specific logic from executor
- [ ] Update tool handler to use capabilities
- [ ] Test auth with both YAML config and env vars
- [ ] Migrate tests
- [ ] Update documentation

## Benefits

1. **Simplified Codebase**: One adapter implementation instead of many
2. **Unified Sessions**: Single cache and message format
3. **Type Safety**: Validated parameters with IDE support
4. **Easy Extensions**: Add new providers by updating LiteLLM adapter
5. **Clean Separation**: No provider logic in framework code

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| LiteLLM missing features | Use `extras` passthrough dict |
| LiteLLM bugs/regressions | Keep old adapters as fallback |
| Performance overhead | Benchmark and optimize hot paths |
| Streaming differences | Verify streaming support per provider |

## Example: Adding a New Provider

To add support for a new provider (e.g., Anthropic):

1. Ensure LiteLLM supports it
2. Add config to `config.yaml` / `secrets.yaml`:
   ```yaml
   providers:
     anthropic:
       api_key: ${ANTHROPIC_API_KEY}
   ```
3. Create param class if needed:
   ```python
   @dataclass
   class AnthropicParams(BaseToolParams):
       max_tokens: Optional[int] = Route.adapter()
   ```
4. Update capability detection in LiteLLM adapter if needed
5. That's it! The adapter will automatically:
   - Extract "anthropic" from "anthropic/claude-3"
   - Get auth config from settings.providers.anthropic
   - Pass it to LiteLLM

## Conclusion

This architecture provides a clean separation between framework and provider concerns while leveraging LiteLLM's unified interface. It maintains type safety, supports provider-specific features, and makes the codebase significantly easier to maintain and extend.
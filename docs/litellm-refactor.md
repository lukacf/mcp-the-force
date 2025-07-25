# Protocol-Based Adapter Architecture

## Overview

This document outlines the architectural refactor to a **protocol-based design**. This design decouples the core framework from provider-specific adapters by defining a clear `MCPAdapter` protocol. While new adapters *can* be implemented using libraries like LiteLLM for simplicity (as seen in the new Grok adapter), the primary goal is adherence to the protocol, not mandating a specific underlying library.

**Status**: Mid-migration. Only Grok has been migrated using the bridge pattern. Other providers (OpenAI, Gemini) still use the legacy BaseAdapter system.

## Design Principles

1. **Protocol Over Inheritance**: Use structural typing (Protocol) instead of base classes
2. **Pattern B for Capabilities**: Compile-time dataclass inheritance for model capabilities
3. **Type Safety**: Use dataclasses and Route descriptors for parameters
4. **Bridge Pattern**: Temporary scaffolding to connect new protocol adapters with legacy system
5. **Unified Interfaces**: Single session cache, consistent tool handling

## Architecture Components

### 1. Adapter Protocol (`mcp_the_force/adapters/protocol.py`)

Defines the `MCPAdapter` protocol that all new adapters must structurally satisfy:

```python
class MCPAdapter(Protocol):
    """Interface that all adapters must satisfy.
    
    This is a Protocol (structural typing) - adapters don't need to
    inherit from this, they just need to have these attributes/methods.
    """
    capabilities: AdapterCapabilities
    param_class: type
    display_name: str
    model_name: str
    
    async def generate(
        self,
        prompt: str,
        params: Any,  # Instance of param_class
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Generate response from the model"""
        ...
```

Also defines the `ToolDispatcher` protocol for standardized tool execution.

### 2. Adapter Capabilities (`mcp_the_force/adapters/capabilities.py`)

Base dataclass using **Pattern B** (inheritance-only) for zero-runtime capability definition:

```python
@dataclass
class AdapterCapabilities:
    """What the framework needs to know about an adapter"""
    native_file_search: bool = False
    supports_functions: bool = True
    supports_streaming: bool = True
    parallel_function_calls: Optional[int] = None
    max_context_window: Optional[int] = None
    supports_live_search: bool = False
    supports_reasoning_effort: bool = False
    supports_vision: bool = False
    description: str = ""
    provider: str = ""
    model_family: str = ""
```

Provider-specific capabilities inherit from this base (see `mcp_the_force/adapters/grok_new/models.py`):

```python
@dataclass
class GrokBaseCapabilities(AdapterCapabilities):
    """Base capabilities shared by all Grok models."""
    native_file_search: bool = False
    supports_functions: bool = True
    supports_streaming: bool = True
    supports_live_search: bool = True
    provider: str = "xai"
    model_family: str = "grok"

@dataclass
class GrokMiniCapabilities(GrokBaseCapabilities):
    """Grok mini models with reasoning effort support."""
    max_context_window: int = 32_000
    supports_reasoning_effort: bool = True
    description: str = "Quick responses with adjustable reasoning effort"
```

### 3. Parameter Classes (`mcp_the_force/adapters/params.py`)

Type-safe parameter definitions using Route descriptors:

```python
class BaseToolParams:
    """Parameters every tool has.
    
    This is not a dataclass - it works with Route descriptors like ToolSpec.
    """
    instructions: ClassVar[RouteDescriptor] = Route.prompt(pos=0, description="User instructions")
    output_format: ClassVar[RouteDescriptor] = Route.prompt(pos=1, description="Expected output format")
    context: ClassVar[RouteDescriptor] = Route.prompt(pos=2, description="Context files/directories")
    session_id: ClassVar[RouteDescriptor] = Route.session(description="Session ID for conversation")

class GrokToolParams(BaseToolParams):
    """Grok-specific parameters."""
    search_mode: ClassVar[RouteDescriptor] = Route.adapter(
        default="auto", description="Live Search mode: 'auto', 'on', 'off'"
    )
    search_parameters: ClassVar[RouteDescriptor] = Route.adapter(
        default=None, description="Live Search parameters"
    )
    # ... more Grok-specific params
```

### 4. Unified Session Cache (`mcp_the_force/unified_session_cache.py`)

Single, provider-agnostic session cache storing conversations in a flexible format:

```python
@dataclass
class UnifiedSession:
    """Session data stored in the cache."""
    session_id: str
    updated_at: int
    history: List[Dict[str, Any]] = field(default_factory=list)  # Flexible format
    provider_metadata: Dict[str, Any] = field(default_factory=dict)  # Provider-specific data
```

Supports both Chat and Responses API formats, with provider-specific metadata.

### 5. Bridge Adapters (Temporary Scaffolding)

The key to migration - bridge adapters that connect new protocol adapters to the legacy system:

```python
# mcp_the_force/adapters/grok_bridge.py
class GrokBridgeAdapter(BaseAdapter):
    """Bridge adapter connecting protocol-based GrokAdapter to legacy system."""
    
    def __init__(self, model_name: str = "grok-4"):
        # Create the protocol-based adapter
        self.protocol_adapter = GrokAdapter(model_name)
        
        # Copy attributes for BaseAdapter compatibility
        self.model_name = self.protocol_adapter.model_name
        self.display_name = self.protocol_adapter.display_name
        self.context_window = self.protocol_adapter.capabilities.max_context_window or 131_000
    
    async def generate(self, prompt: str, **kwargs) -> Union[str, Dict[str, Any]]:
        """Translate legacy generate call to protocol generate."""
        # Extract parameters
        vector_store_ids = kwargs.get("vector_store_ids")
        session_id = kwargs.get("session_id")
        # ... extract more params
        
        # Create protocol objects
        params = SimpleNamespace(
            instructions=prompt,
            output_format="",
            context=[],
            session_id=session_id or "",
            search_mode=search_mode,
            # ... more params
        )
        
        ctx = CallContext(
            session_id=session_id or "",
            vector_store_ids=vector_store_ids,
        )
        
        tool_dispatcher = ToolDispatcher(vector_store_ids=vector_store_ids)
        
        # Call protocol adapter
        return await self.protocol_adapter.generate(
            prompt=prompt,
            params=params,
            ctx=ctx,
            tool_dispatcher=tool_dispatcher,
            **kwargs,
        )
```

## The Migration Path: A Step-by-Step Guide

Using Grok as the canonical example:

### 1. Create New Adapter Package
```bash
mcp_the_force/adapters/grok_new/
├── __init__.py
├── adapter.py      # Protocol-based adapter
└── models.py       # Pattern B capabilities
```

### 2. Define Capabilities (Pattern B)
```python
# grok_new/models.py
@dataclass
class GrokBaseCapabilities(AdapterCapabilities):
    """Base for all Grok models"""
    # ... common capabilities

@dataclass  
class Grok4Capabilities(GrokBaseCapabilities):
    """Grok 4 specific"""
    max_context_window: int = 256_000
    description: str = "Advanced multi-agent reasoning"

# Registry
GROK_MODEL_CAPABILITIES = {
    "grok-4": Grok4Capabilities(),
    # ... more models
}
```

### 3. Implement Protocol-Based Adapter
```python
# grok_new/adapter.py
class GrokAdapter:  # Note: NO inheritance!
    """Protocol-based Grok adapter using LiteLLM."""
    
    def __init__(self, model: str = "grok-4"):
        self.model_name = model
        self.capabilities = GROK_MODEL_CAPABILITIES[model]
        self.param_class = GrokToolParams
        # ...
    
    async def generate(
        self,
        prompt: str,
        params: GrokToolParams,
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        # Implementation using LiteLLM
```

### 4. Create Parameter Class
Add to `mcp_the_force/adapters/params.py`:
```python
class GrokToolParams(BaseToolParams):
    """Grok-specific parameters"""
    search_mode: ClassVar[RouteDescriptor] = Route.adapter(default="auto")
    # ... more params
```

### 5. Create Bridge Adapter
```python
# mcp_the_force/adapters/grok_bridge.py
class GrokBridgeAdapter(BaseAdapter):
    """Temporary bridge to legacy system"""
    # See example above
```

### 6. Register Bridge
In `mcp_the_force/adapters/__init__.py`:
```python
def get_adapter(adapter_type: str) -> BaseAdapter:
    # ... existing code ...
    
    # Lazy loading for new protocol adapters
    if adapter_type == "xai_protocol":
        from .grok_bridge import GrokBridgeAdapter
        return GrokBridgeAdapter
```

### 7. Update Tool Definitions
In `mcp_the_force/tools/definitions.py`:
```python
@tool
class ChatWithGrok4(ToolSpec):
    model_name = "grok-4"
    adapter_class = "xai_protocol"  # Changed from "xai"
    # ... rest unchanged
```

## Current Status

### Completed
- ✅ Protocol definitions (MCPAdapter, ToolDispatcher)
- ✅ Capabilities with Pattern B (AdapterCapabilities + inheritance)
- ✅ Parameter classes with Route descriptors
- ✅ Unified session cache
- ✅ Grok adapter migration (using bridge pattern)
- ✅ Tool updates for Grok

### In Progress
- 🔄 OpenAI adapter migration
- 🔄 Gemini adapter migration
- 🔄 Removal of provider-specific session caches

### TODO
- [ ] Migrate remaining adapters (OpenAI, Gemini)
- [ ] Remove legacy adapters after migration
- [ ] Remove bridge adapters once framework is updated
- [ ] Update executor to work directly with protocol adapters
- [ ] **Dynamic System Prompt Generation** (see below)
- [ ] Add concurrency protection to unified cache
- [ ] Remove scattered provider checks (`if adapter == "xai"`)

## Dynamic System Prompt Generation (TODO)

Current system prompts are hardcoded in `prompts.py`. We should generate them dynamically based on capabilities:

```python
def generate_system_prompt(
    capabilities: AdapterCapabilities,
    available_tools: List[str],
    model_specific_info: Optional[str] = None
) -> str:
    """Generate system prompt based on model capabilities."""
    # Use capabilities to build appropriate prompt
    # - supports_live_search → Mention Live Search
    # - supports_vision → Mention multimodal
    # - available_tools → Only mention tools that are available
    # - etc.
```

Benefits:
- Eliminates hardcoded prompts
- Automatically adapts to new models
- Uses capabilities we've already defined
- Scales without code changes

## Lessons Learned

1. **Protocol > Inheritance**: The Protocol approach provides flexibility without tight coupling
2. **Pattern B Works Well**: Simple dataclass inheritance for capabilities is clean and type-safe
3. **Bridge Pattern is Essential**: Allows gradual migration without breaking the system
4. **LiteLLM is Optional**: It's a useful implementation detail, not a requirement
5. **Route Descriptors Need Care**: Can't use with dataclasses, need regular classes with ClassVar

## Benefits of Final Architecture

1. **Clean Separation**: Adapters are truly isolated
2. **Type Safety**: Full typing with dataclasses and protocols
3. **Gradual Migration**: Bridge pattern allows incremental updates
4. **Future Proof**: Easy to add new providers or swap implementations
5. **Zero Runtime Logic**: Pattern B capabilities are defined at compile time

## Next Steps

1. Continue migrating adapters one by one using the established pattern
2. Test each migration thoroughly before moving to the next
3. Once all adapters are migrated, update the framework to use protocols directly
4. Remove bridge adapters and legacy code
5. Implement dynamic system prompt generation
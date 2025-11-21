# Protocol-Based Grok Adapter

This is a complete reimplementation of the Grok adapter following the protocol-based architecture described in `docs/litellm-refactor.md`.

## Architecture Components

1. **AdapterCapabilities** (`capabilities.py`): Dataclass declaring what the adapter can do
2. **GrokToolParams** (`params.py`): Type-safe parameter definitions using Route descriptors
3. **MCPAdapter Protocol** (`protocol.py`): Interface that adapters must satisfy
4. **GrokAdapter** (`adapter.py`): Protocol-based implementation using LiteLLM
5. **GrokBridgeAdapter** (`grok_bridge.py`): Bridge for legacy BaseAdapter compatibility
6. **ToolDispatcher** (`tool_dispatcher.py`): Tool execution interface implementation

## Key Features

- ✅ Supports all 7 Grok models (grok-3-beta, grok-3-fast, grok-4.1, grok-4.1-heavy, grok-3-mini, grok-3-mini-beta, grok-3-mini-fast)
- ✅ Live Search (web/X search) with proper parameter handling
- ✅ Session continuation using unified session cache
- ✅ Tool calling with OpenAI-compatible format
- ✅ Structured output support
- ✅ Reasoning effort for mini models
- ✅ Type-safe parameters with validation
- ✅ Protocol-based design (no inheritance required)
- ✅ Self-contained authentication

## Usage

### Direct Protocol Usage (Future)
```python
from mcp_the_force.adapters.grok_new import GrokAdapter
from mcp_the_force.adapters.params import GrokToolParams
from mcp_the_force.adapters.protocol import CallContext
from mcp_the_force.adapters.tool_dispatcher import ToolDispatcher

# Create adapter
adapter = GrokAdapter("grok-4.1")

# Create parameters
params = GrokToolParams(
    instructions="Hello",
    output_format="Brief",
    context=[],
    session_id="test-session",
    search_mode="on",
    temperature=0.7
)

# Create context
ctx = CallContext(session_id="test-session")

# Create tool dispatcher
dispatcher = ToolDispatcher()

# Generate
result = await adapter.generate(
    prompt="What's the weather like?",
    params=params,
    ctx=ctx,
    tool_dispatcher=dispatcher
)
```

### Legacy System Usage (Current)
```python
# The bridge adapter is registered as "xai_protocol"
adapter = get_adapter("xai_protocol", "grok-4.1")

# Use like any other BaseAdapter
result = await adapter.generate(
    prompt="Hello",
    session_id="test-session",
    search_mode="on"
)
```

## Testing

Use the `TestGrokProtocol` tool to test the implementation:

```
test_grok_protocol("Test basic functionality", "Just say hello", [], "protocol-test-001")
```

## Migration Path

1. **Current**: Using `GrokBridgeAdapter` to maintain compatibility
2. **Next**: Update executor to work with Protocol-based adapters directly
3. **Future**: Remove BaseAdapter inheritance entirely

## Benefits

- **Type Safety**: Parameters are validated at the type level
- **Protocol-based**: No inheritance required, just structural typing
- **Unified Sessions**: Single cache for all providers
- **Clean Separation**: No provider logic in framework code
- **Easy Extension**: Add new models by updating GROK_MODELS dict
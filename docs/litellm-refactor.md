# Protocol-Based Adapter Architecture

## Overview

This document describes the protocol-based adapter architecture for the MCP The-Force server. The architecture provides a clean, extensible system for integrating AI models while maintaining type safety, capability-aware validation, and excellent developer experience.

**Status**: Fully designed, implementation in progress.

## Core Concepts

### 1. Protocol-Based Design

All adapters implement the `MCPAdapter` protocol without inheritance:

```python
class MCPAdapter(Protocol):
    """Protocol that all adapters must satisfy."""
    param_class: Type[Any]           # Links to parameter class
    capabilities: AdapterCapabilities # What the model can do
    
    async def generate(
        self,
        prompt: str,
        params: Any,              # Instance of param_class
        ctx: CallContext,
        *,
        tool_dispatcher: ToolDispatcher,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Generate response from the model."""
        ...
```

### 2. Single Source of Truth

Each adapter has a `definitions.py` file that contains:
- Capability classes
- Parameter class with Route descriptors
- Model registry
- Blueprint generation

This eliminates the need to edit multiple files when adding models or features.

### 3. Enhanced Route Descriptors

Route descriptors now include capability requirements:

```python
class OpenAIToolParams(BaseToolParams):
    reasoning_effort: str = Route.adapter(
        default="medium",
        description="Reasoning effort level",
        requires_capability=lambda c: c.supports_reasoning_effort
    )
```

The lambda provides type-safe, IDE-friendly capability validation.

## Architecture Components

### 1. Adapter Structure

Each adapter is a self-contained package:

```
mcp_the_force/adapters/openai/
├── __init__.py
├── adapter.py          # MCPAdapter implementation
├── definitions.py      # Single source of truth
├── flow.py            # Provider-specific logic
└── client.py          # API client management
```

### 2. The definitions.py Pattern

```python
# adapters/openai/definitions.py

# 1. Parameter class with capability requirements
class OpenAIToolParams(BaseToolParams):
    temperature: float = Route.adapter(
        default=0.2,
        requires_capability=lambda c: c.supports_temperature
    )
    
    reasoning_effort: str = Route.adapter(
        default="medium",
        requires_capability=lambda c: c.supports_reasoning_effort
    )

# 2. Capability definitions
@dataclass
class O3Capabilities(AdapterCapabilities):
    supports_reasoning_effort: bool = True
    supports_temperature: bool = False  # o3 doesn't support temperature!
    max_context_window: int = 200_000

# 3. Model registry
OPENAI_MODEL_CAPABILITIES = {
    "o3": O3Capabilities(),
    "o3-pro": O3ProCapabilities(),
    "gpt-4.1": GPT41Capabilities(),
}

# 4. Blueprint generation
def _generate_and_register_blueprints():
    for model_name, capabilities in OPENAI_MODEL_CAPABILITIES.items():
        blueprint = ToolBlueprint(
            model_name=model_name,
            adapter_key="openai",
            param_class=OpenAIToolParams,
            description=capabilities.description,
            timeout=_calculate_timeout(model_name),
            context_window=capabilities.max_context_window,
        )
        register_blueprints([blueprint])

# Auto-register on import
_generate_and_register_blueprints()
```

### 3. Validation Chain

The system provides multi-layered validation:

```
MCP Request
    ↓
ParameterValidator      # Type checking, required fields
    ↓
CapabilityValidator     # Model-specific capability validation
    ↓
ParameterRouter        # Routes to adapter/prompt/session
    ↓
Adapter                # Provider-specific validation
    ↓
API Call
```

Example validation error:
```
ValueError: Parameter 'temperature' requires capability 'supports_temperature' 
            which model 'o3' doesn't support
```

### 4. Tool Generation Flow

```
Import adapter package → definitions.py runs → Blueprints registered
                                                        ↓
                                                  make_tool()
                                                        ↓
                                                 Dynamic tool class
                                                        ↓
                                                 @tool decorator
                                                        ↓
                                                 MCP registration
```

### 5. Route Descriptor System

Routes declare both destination and validation:

```python
@dataclass
class RouteDescriptor:
    route: RouteType                               # WHERE it goes
    default: Any = _NO_DEFAULT                     # Default value
    description: Optional[str] = None              # Documentation
    position: Optional[int] = None                 # Argument order
    requires_capability: Optional[Callable] = None # WHEN it's valid
```

## Implementation Guide

### Adding a New Model

1. Edit the adapter's `definitions.py`:
```python
# Add capability class
@dataclass
class NewModelCapabilities(BaseCapabilities):
    supports_new_feature: bool = True
    max_context_window: int = 100_000

# Add to registry
OPENAI_MODEL_CAPABILITIES = {
    # ... existing models ...
    "new-model": NewModelCapabilities(),
}
```

That's it! Blueprint generation handles the rest.

### Adding a New Parameter

1. Edit the adapter's `definitions.py`:
```python
class OpenAIToolParams(BaseToolParams):
    # ... existing params ...
    
    new_feature: str = Route.adapter(
        default="standard",
        description="New feature mode",
        requires_capability=lambda c: c.supports_new_feature
    )
```

2. Update the capability class:
```python
@dataclass
class AdapterCapabilities:
    # ... existing capabilities ...
    supports_new_feature: bool = False
```

### Creating a New Adapter

1. Create adapter package:
```bash
mcp_the_force/adapters/newprovider/
├── __init__.py
├── adapter.py
└── definitions.py
```

2. Implement in `definitions.py`:
```python
# Parameters
class NewProviderToolParams(BaseToolParams):
    custom_param: str = Route.adapter(default="value")

# Capabilities
@dataclass
class NewProviderCapabilities(AdapterCapabilities):
    provider: str = "newprovider"
    supports_streaming: bool = True

# Models
NEW_PROVIDER_MODELS = {
    "model-1": NewProviderCapabilities(),
}

# Generate blueprints
_generate_and_register_blueprints()
```

3. Implement adapter:
```python
class NewProviderAdapter:
    param_class = NewProviderToolParams
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.capabilities = NEW_PROVIDER_MODELS[model_name]
    
    async def generate(self, prompt, params, ctx, *, tool_dispatcher, **kwargs):
        # Implementation
```

4. Register in `adapters/registry.py`:
```python
_ADAPTER_REGISTRY = {
    # ... existing ...
    "newprovider": ("mcp_the_force.adapters.newprovider.adapter", "NewProviderAdapter"),
}
```

## Benefits

1. **Type Safety**: Lambda-based capability requirements with IDE support
2. **Single Source of Truth**: One file to edit per adapter
3. **Early Validation**: Catches errors before expensive API calls
4. **Clear Errors**: Users know exactly why parameters fail
5. **Extensible**: New adapters follow the established pattern
6. **DRY**: No duplication between capabilities and parameters

## Implementation Task List

This is a linear, zero-shot implementation plan. No backwards compatibility, no gradual migration.

### Phase 1: Core Infrastructure (Do First)

1. **Update RouteDescriptor** (`tools/descriptors.py`)
   - Add `requires_capability: Optional[Callable[[Any], bool]] = None` field
   - Update `Route.adapter()` to accept `requires_capability` parameter

2. **Update ParameterInfo** (`tools/registry.py`)
   - Add `requires_capability: Optional[Callable] = None` field
   - Update parameter extraction to preserve capability requirements

3. **Enhance ToolDispatcher Protocol** (`adapters/tool_dispatcher.py`)
   - Add `execute_batch(tool_calls: List[ToolCall]) -> List[str]` method
   - Ensure parallel execution capability for OpenAI compatibility
   - Update ToolHandler implementation to support batch execution

4. **Create CapabilityValidator** (`tools/capability_validator.py`)
   - New class that validates parameters against model capabilities
   - Method: `validate_against_capabilities(metadata, kwargs, capabilities)`
   - Execute lambdas and provide clear error messages
   - Skip capability checks (only) for local tools where `capabilities is None`
   - Error format: `"Parameter 'X' is not supported by model 'Y' because its 'capability_Z' is False"`

5. **Update ToolMetadata** (`tools/registry.py`)
   - Add `capabilities: Optional[AdapterCapabilities] = None` field
   - Store model capabilities during tool registration

6. **Update ToolExecutor** (`tools/executor.py`)
   - Add `capability_validator = CapabilityValidator()` 
   - Get capabilities from metadata instead of instantiating adapter
   - Call capability validator after basic validation
   - Ensure local tools (adapter_class = None) still get full parameter validation

### Phase 2: Adapter Migration (Do in Order)

#### 2.1 OpenAI Adapter

5. **Create definitions.py** (`adapters/openai/definitions.py`)
   - Move `OpenAIToolParams` from central params.py
   - Add capability requirements to each parameter
   - Move model capabilities from models.py
   - Add blueprint generation logic

6. **Update OpenAI adapter** (`adapters/openai/adapter.py`)
   - Import from local definitions
   - Reference `self.param_class = OpenAIToolParams`
   - Remove any redundant validation

7. **Update OpenAI flow.py** (`adapters/openai/flow.py`)
   - Remove local ToolExecutor import
   - Update to use passed-in tool_dispatcher
   - Preserve parallel execution using `tool_dispatcher.execute_batch()`
   - Remove the BuiltInToolDispatcher class

8. **Delete tool_exec.py** (`adapters/openai/tool_exec.py`)
   - Delete file after flow.py is updated
   - Verify no other imports reference it

#### 2.2 Google Adapter

9. **Create definitions.py** (`adapters/google/definitions.py`)
   - Move `GeminiToolParams` from central params.py
   - Add capability requirements
   - Consolidate model definitions
   - Add blueprint generation

10. **Update Google adapter** (`adapters/google/adapter.py`)
    - Import from local definitions
    - Reference local param class

#### 2.3 XAI Adapter

11. **Create definitions.py** (`adapters/xai/definitions.py`)
    - Move `GrokToolParams` from central params.py
    - Add capability requirements
    - Consolidate model definitions
    - Add blueprint generation

12. **Update XAI adapter** (`adapters/xai/adapter.py`)
    - Import from local definitions
    - Reference local param class

### Phase 3: Cleanup

13. **Clean central params.py** (`adapters/params.py`)
    - Remove all adapter-specific param classes
    - Keep only `BaseToolParams`
    - Add clear documentation about inheritance pattern

14. **Update adapter __init__.py files**
    - Import from definitions to trigger blueprint registration
    - Ensure proper exports

15. **Update tools/autogen.py**
    - Simplify to just import adapter packages
    - Remove any adapter-specific logic

16. **Update blueprint processing** (`tools/factories.py`)
    - Extract capabilities from adapter during tool generation
    - Store capabilities in ToolMetadata
    - Ensure local tools have None capabilities

17. **Add registration validation** (`tools/blueprint_registry.py`)
    - Validate blueprints at registration time
    - Check parameter-capability consistency
    - Ensure all required fields present

### Phase 4: Testing & Verification

18. **Update unit tests**
    - Fix imports to use local param classes
    - Update mocks to include capabilities
    - Add capability validation tests
    - Test clear error message format

19. **Integration testing**
    - Test each adapter with valid parameters
    - Test each adapter with invalid parameters (capability mismatch)
    - Verify error messages match expected format
    - Test local tools still get full parameter validation

20. **Parallel execution testing**
    - Verify OpenAI adapter maintains parallel tool execution
    - Test batch execution performance
    - Ensure other adapters work with new ToolDispatcher

21. **End-to-end testing**
    - Test actual tool calls through MCP
    - Verify validation happens at right stage
    - Confirm performance is acceptable
    - Test error propagation to MCP clients

### Phase 5: Documentation

22. **Update inline documentation**
    - Add docstrings explaining capability requirements
    - Document the lambda pattern
    - Add examples of capability validation
    - Document parallel vs serial tool execution

23. **Update README/guides**
    - Document how to add new models
    - Document how to add new parameters
    - Include troubleshooting guide
    - Add migration guide for any external consumers

### Completion Checklist

- [ ] All adapters use local definitions.py
- [ ] No adapter-specific code in central files
- [ ] Capability validation works for all parameters
- [ ] Clear error messages for capability mismatches
- [ ] All tests pass
- [ ] Documentation is complete

---

# Legacy System Documentation

## Original Bridge Pattern Migration

The initial refactor used a bridge pattern to migrate from inheritance-based to protocol-based adapters. This section documents the original approach for historical context.

### Bridge Adapter Pattern

The migration used bridge adapters to connect new protocol adapters to the legacy BaseAdapter system:

```python
class GrokBridgeAdapter(BaseAdapter):
    """Bridge connecting protocol adapter to legacy system."""
    
    def __init__(self, model_name: str):
        self.protocol_adapter = GrokAdapter(model_name)
        # Copy attributes for BaseAdapter compatibility
        
    async def generate(self, prompt: str, **kwargs):
        # Translate legacy call to protocol call
        params = SimpleNamespace(...)
        ctx = CallContext(...)
        return await self.protocol_adapter.generate(...)
```

### Migration Status (Historical)

- ✅ Grok migrated with bridge pattern
- ✅ Protocol definitions created
- ✅ Unified session cache implemented
- ❌ OpenAI and Gemini remained on BaseAdapter

### Lessons from Bridge Pattern

1. **Gradual migration worked** but added complexity
2. **Two systems in parallel** created confusion
3. **Parameter extraction** was error-prone
4. **Direct protocol adoption** would have been cleaner

The current architecture eliminates bridges entirely, with all adapters implementing the protocol directly.
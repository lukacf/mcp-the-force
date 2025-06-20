# Migration Guide: YAML to Dataclass-Based Tools

This guide explains the migration from the YAML-based configuration system to the new dataclass-based tool system.

## What Changed

### Before (YAML-based)
- Tool definitions in `models.yaml`
- Dynamic function generation from YAML
- Provider-specific hardcoding in server

### After (Dataclass-based)
- Tool definitions as Python classes
- Type-safe, IDE-friendly code
- Clean routing via descriptors

## Architecture Overview

### 1. Tool Definitions
Tools are now Python classes decorated with `@tool`:

```python
@tool
class VertexGemini25Pro(ToolSpec):
    """Tool description."""
    model_name = "gemini-2.5-pro"
    adapter_class = "vertex"
    
    # Parameters with routing
    instructions: str = Route.prompt(pos=0)
    temperature: float = Route.adapter(default=0.2)
```

### 2. Route Descriptors
Parameters declare where they're routed:
- `Route.prompt()` - Goes to prompt builder
- `Route.adapter()` - Goes to model adapter
- `Route.vector_store()` - Triggers vector store creation
- `Route.session()` - Handles session management

### 3. Benefits
- **Type Safety**: Full IDE support, autocomplete
- **No YAML Parsing**: No runtime errors from typos
- **Single Source**: Code is the specification
- **Extensible**: Easy to add new routing types

## Adding New Tools

1. Create a new class in `tools/definitions.py`:
```python
@tool
class MyNewTool(ToolSpec):
    model_name = "my-model"
    adapter_class = "my-adapter"
    context_window = 100_000
    
    instructions: str = Route.prompt(pos=0)
    custom_param: str = Route.adapter()
```

2. The tool is automatically registered on import
3. No server code changes needed

## Removed Files
- `model_config/models.yaml` - No longer needed
- `model_config/` directory - Can be deleted
- Old server code - Backed up as `server_old.py`
# Architecture Analysis: What Happened and Where We Are

## Timeline of Events

1. **14:30** - Last commit before big refactor: `9860deb cleanup: Remove TestOpenAIProtocol tool`
2. **14:42** - architecture-refactor-gemini-001: Initial architectural discussion
3. **15:55** - architecture-refactor-o3-001: O3 review of the architecture
4. **16:05** - architecture-review-gemini-001: Implementation review
5. **16:08** - architecture-review-gemini-002: Bug hunting
6. **16:32** - refactor-review-gemini-001: Final review
7. **17:18** - test session: Started hitting errors

## Original Architecture Vision (from conversations)

### Core Principles:
1. **NO hard-coded adapter-specific stuff** in levels above the adapters
2. **Dynamic tool generation** from adapter capabilities
3. **Protocol-based adapters** using Python Protocols (not inheritance)
4. **Route descriptor system** as the "pride and joy" - elegant parameter routing
5. **Blueprint system** for tool definitions

### Key Components:

1. **Route Descriptors** (the good part we want to keep):
   ```python
   instructions: str = Route.prompt(pos=0, description="Task instructions")
   temperature: float = Route.adapter(default=0.7, description="Sampling temperature")
   ```

2. **ToolSpec Classes**:
   - NOT dataclasses for holding data
   - Static definitions/schemas describing tools
   - Use Route descriptors to define parameter routing

3. **Blueprint System**:
   - Adapters expose blueprints of their capabilities
   - Factory generates tool classes from blueprints
   - Tools auto-register with MCP

4. **Parameter Flow**:
   - User provides parameters to tool
   - Executor validates and routes parameters based on Route descriptors
   - Adapters receive routed parameters (not instantiated classes)

## What Went Wrong

### The Original Sin:
When I got the error "GeminiToolParams.__init__() got an unexpected keyword argument 'messages'", I made the wrong fix:
- **Wrong**: Converted param classes to dataclasses
- **Right**: Should have investigated why 'messages' was being passed

### The Cascade:
1. Made param classes into dataclasses
2. This broke the Route descriptor system
3. Tools started getting empty parameters
4. I tried to fix by changing routing to Route.prompt()
5. User pointed out "Our parameters are not 'prompt'"
6. Realized I had fundamentally broken the architecture

## Current State

### What's Broken:
1. **executor.py** tries to instantiate param_class like a dataclass
2. **Adapters** expect params to be an instance with attributes
3. **params.py** has Route descriptors but isn't a proper dataclass
4. **SearchProjectHistory** is broken (missing adapter_class in model_config)

### What's Working:
1. Protocol-based adapters are implemented
2. Blueprint system generates tools dynamically
3. Route descriptors are restored in params.py
4. Tool registration with MCP works

## The Correct Architecture

### Key Discovery: RouteDescriptor is a Python Descriptor

RouteDescriptor implements `__get__` and `__set__` methods, making it a proper Python descriptor. This means:
- When you access an attribute on an instance, it calls `__get__`
- When you set an attribute on an instance, it calls `__set__`
- The descriptor stores values with a `_` prefix on the instance

### How It ACTUALLY Should Work:

1. **ToolSpec/Param Classes**:
   - Use RouteDescriptor as class attributes (with ClassVar)
   - CAN be instantiated as objects!
   - RouteDescriptors act as properties on instances
   - Define WHERE parameters come from AND store values

2. **Parameter Flow**:
   ```
   User Input → Validator → Router → Create Param Instance → Adapter
   ```
   - Router uses Route descriptors to organize parameters
   - Executor creates an instance of param_class
   - Adapter receives param instance with populated attributes
   - Access via `params.temperature`, `params.session_id`, etc.

3. **Adapter Protocol**:
   ```python
   async def generate(
       self,
       prompt: str,
       params: Any,  # Instance of param_class with RouteDescriptors
       ctx: CallContext,
       tool_dispatcher: ToolDispatcher,
       **kwargs
   ) -> Dict[str, Any]
   ```

4. **Blueprint System**:
   - Adapter defines blueprint with param_class reference
   - Factory copies Route descriptors from param_class
   - Generated tools use these descriptors for routing

### The Missing Piece

The param classes need a way to be instantiated. Options:
1. Add `__init__` method that accepts kwargs
2. Use a metaclass to generate `__init__`
3. Use `@dataclass_transform` decorator (like ToolSpec does)
4. Create instances manually by setting attributes

## Current Critical Issues

### 1. Circular Import
```
params.py → tools.descriptors → tools/__init__ → definitions → 
search_history → memory.config → utils.vector_store → 
adapters.openai.client → adapters.openai → adapter → params.py
```

This prevents even basic testing of the param classes.

### 2. Param Class Instantiation
The current code expects to instantiate param classes, but they:
- Have ClassVar[RouteDescriptor] attributes
- Don't have an `__init__` method
- Can't be instantiated with `BaseToolParams(**kwargs)`

### 3. Architectural Confusion
Two conflicting patterns exist:
- MockAdapter uses a @dataclass for params (simple, works)
- Real adapters use Route descriptors (complex, broken)

## Next Steps

1. **Fix circular import**: Move OpenAIClientFactory out of adapters
2. **Decide on param class design**:
   - Option A: Make them proper classes with `__init__`
   - Option B: Use dataclasses like MockAdapter
   - Option C: Create a factory to build instances with descriptors
3. **Fix SearchProjectHistory**: Add missing adapter_class
4. **Test the system**: Ensure parameters flow correctly

## Key Questions for Agreement

1. Should param classes be instantiable objects or just schemas?
2. If objects, how should they be instantiated?
3. Should we use Route descriptors in param classes or just in ToolSpec?
4. Is the circular import a symptom of a deeper architectural issue?

## Agreed Architecture (Based on O3's Recommendation)

### Core Insight: Two Orthogonal Axes

1. **Execution Engines**:
   - **LLM-adapter engine**: `generate()` → calls external model
   - **Local-service engine**: `execute()` → runs pure Python, DB queries, etc.

2. **Exposure Modes**:
   - **MCP tool**: Claude can invoke directly
   - **LLM built-in function**: OpenAI/Gemini/Grok call via ToolDispatcher

### Key Architectural Decisions

1. **LocalService Protocol**:
   ```python
   class LocalService(Protocol):
       async def execute(self, **kwargs) -> str: ...
   ```
   - No BaseAdapter fields
   - No model_name/context_window
   - Pure execution logic

2. **ToolSpec Enhancement**:
   - Add `service_cls` attribute for local services
   - Keep `adapter_class` for AI adapters
   - Route descriptors remain unchanged

3. **Executor Dispatch**:
   ```python
   if metadata.model_config.get("service_cls"):
       service = metadata.model_config["service_cls"]()
       return await service.execute(**adapter_params)
   else:
       # Existing adapter logic
   ```

4. **Dual Exposure**:
   - Same LocalService backs both MCP and LLM function calls
   - ToolDispatcher calls execute() for built-in functions
   - No duplication, guaranteed parity

### Benefits

- Clear separation of concerns
- No meaningless fields (model_name on utilities)
- Type safety preserved
- No circular imports (LocalService in tools/, not adapters/)
- Easy migration path

### Migration Plan

1. Create LocalService protocol in tools/
2. Convert SearchHistoryAdapter → SearchHistoryService
3. Convert LoggingAdapter → LoggingService
4. Update ToolSpec classes: adapter_class → service_cls
5. Add dispatch logic to executor
6. Remove BaseAdapter imports from utilities
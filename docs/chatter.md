# Chatter: Multi-Model Collaboration Feature

## Overview

Chatter enables multiple AI models to work together on complex problems through structured, multi-turn conversations. Models share a "whiteboard" where they can contribute ideas, review others' work, and build solutions collaboratively.

## Architecture: Whiteboard Vector Store Pattern

Based on GPT-5's critical review, we'll implement a "whiteboard vector store" approach that leverages existing MCP infrastructure without requiring adapter changes.

### Core Components

1. **Whiteboard Vector Store**: Dedicated vector store per collaboration session
2. **Meta-Tool Session**: Human-readable transcript in `UnifiedSessionCache`
3. **Collaboration Service**: Orchestrates model turns and manages state
4. **File-Based Communication**: Models access shared context via `file_search`

## Critical Integration Requirements

**ESSENTIAL**: Based on GPT-5's review, these fixes are required for the architecture to work:

### 1. Executor Vector Store Passthrough
- **Issue**: Current `ToolExecutor` only propagates `vector_store_ids` for tools that declare it as a parameter. Chat tools don't have this parameter.
- **Fix**: Add privileged `vector_store_ids` kwarg support in `tools/executor.py`:
  ```python
  # In executor.execute(), before parameter routing:
  vector_store_override = kwargs.pop('vector_store_ids', None)
  # After optimizer/attachments logic:
  if vector_store_override:
      vector_store_ids.extend(vector_store_override)
  ```

### 2. Whiteboard Store Provider Selection  
- **Strategy**: Try OpenAI first (enables native `file_search`), fallback to HNSW
- **Implementation**: Store provider choice in session metadata for consistency across turns

### 3. Message Storage Separation
- **UnifiedSessionCache**: Store ordered transcript for humans (chronological view)
- **Vector Store**: Store searchable content for models (retrieval view)
- **Don't**: Try to retrieve ordered messages from vector store (no list API)

## Implementation Plan (TDD Approach)

### Phase 1: Core Infrastructure & Executor Fix

#### 1.1 Executor Passthrough Fix
- **File**: `mcp_the_force/tools/executor.py`  
- **Change**: Add privileged `vector_store_ids` kwarg support
- **Test**: `tests/unit/test_executor_vector_store_passthrough.py`

```python
def test_executor_passthrough_vector_store_ids():
    """Test executor accepts vector_store_ids for tools that don't declare it"""
    # Test that calling executor.execute(..., vector_store_ids=["vs_123"]) 
    # causes ToolDispatcher to receive the vector store IDs
```

#### 1.2 Test Setup  
- **File**: `tests/unit/test_collaboration_service.py`
- **Mocks**: 
  - `MockVectorStoreManager`
  - `MockUnifiedSessionCache` 
  - `MockToolExecutor`
- **Critical Integration Tests**:
  - Whiteboard vector store attachment reaches adapters
  - Provider fallback (OpenAI → HNSW)
  - History isolation (`disable_history_record=True`)

#### 1.3 Core Data Types
- **File**: `mcp_the_force/types/collaboration.py`
- **Classes**:
  ```python
  @dataclass
  class CollaborationMessage:
      speaker: str  # "user" | model_name
      content: str
      timestamp: datetime
      metadata: Dict[str, Any] = field(default_factory=dict)
  
  @dataclass 
  class CollaborationSession:
      session_id: str
      objective: str
      models: List[str]
      messages: List[CollaborationMessage]
      current_step: int
      mode: Literal["round_robin", "orchestrator"] 
      max_steps: int
      status: Literal["active", "completed", "failed"]
  
  @dataclass
  class CollaborationConfig:
      max_steps: int = 10
      parallel_limit: int = 1
      timeout_per_step: int = 300
      summarization_threshold: int = 50  # messages
      cost_limit_usd: Optional[float] = None
  ```

**Tests to Write First**:
```python
def test_collaboration_message_serialization():
    """Test message can be serialized to/from dict"""
    
def test_collaboration_session_state_transitions():
    """Test session moves through states correctly"""
    
def test_collaboration_config_validation():
    """Test config validates constraints"""
```

### Phase 2: Whiteboard Management

#### 2.1 Whiteboard Manager
- **File**: `mcp_the_force/local_services/whiteboard_manager.py`
- **Class**: `WhiteboardManager`
- **Responsibilities**:
  - Create/manage collaboration vector stores
  - Append messages as VSFiles
  - Handle summarization/rollover
  - Provide search interface

```python
class WhiteboardManager:
    def __init__(self, vector_store_manager: VectorStoreManager):
        self.vs_manager = vector_store_manager
    
    async def create_whiteboard(self, session_id: str) -> Dict[str, str]:
        """Create dedicated vector store for collaboration"""
        # Returns {"store_id": str, "provider": str}
        # Try OpenAI first (enables native file_search), fallback to HNSW
    
    async def append_message(self, session_id: str, message: CollaborationMessage) -> None:
        """Add message as VSFile to whiteboard"""
        # VSFile path: whiteboard/{session_id}/{idx:04d}_{speaker}.txt
    
    async def get_store_info(self, session_id: str) -> Dict[str, str]:
        """Get existing whiteboard store info from session metadata"""
    
    async def summarize_and_rollover(self, session_id: str, threshold: int) -> None:
        """Summarize old messages and create new store (HNSW can't delete files)"""
```

**Tests to Write First**:
```python
def test_create_whiteboard_openai_first():
    """Test whiteboard tries OpenAI first, returns store_id and provider"""
    
def test_create_whiteboard_fallback_to_hnsw():
    """Test fallback to HNSW when OpenAI unavailable"""
    
def test_append_message_creates_vsfile():
    """Test message stored as VSFile with correct path pattern"""
    
def test_get_store_info_from_session_metadata():
    """Test store info retrieval from UnifiedSessionCache metadata"""
    
def test_summarization_rollover_new_store():
    """Test rollover creates new store (HNSW can't delete files)"""
```

#### 2.2 Message Serialization
- **File**: `mcp_the_force/utils/message_serializer.py`
- **Functions**:
  - `message_to_vsfile()`: Convert CollaborationMessage to VSFile
  - `vsfile_to_message()`: Parse VSFile back to CollaborationMessage  
  - `format_whiteboard_context()`: Create search-friendly summaries

### Phase 3: Collaboration Service

#### 3.1 Core Service
- **File**: `mcp_the_force/local_services/collaboration_service.py`
- **Class**: `CollaborationService`

```python
class CollaborationService:
    def __init__(self, 
                 executor: ToolExecutor,
                 whiteboard_manager: WhiteboardManager,
                 session_cache: UnifiedSessionCache):
        self.executor = executor
        self.whiteboard = whiteboard_manager
        self.session_cache = session_cache
    
    async def execute(self, 
                     session_id: str,
                     objective: str,
                     models: List[str],
                     user_input: str = "",
                     config: CollaborationConfig = None) -> str:
        """Main orchestration logic"""
        
    async def _run_round_robin_turn(self, session: CollaborationSession) -> None:
        """Execute next model in round-robin sequence"""
        
    async def _run_orchestrator_turn(self, session: CollaborationSession) -> None:
        """Let orchestrator model decide next step"""
        
    async def _execute_model_turn(self, 
                                 model_name: str, 
                                 session: CollaborationSession) -> str:
        """Execute single model turn with whiteboard context"""
        # Always set disable_history_record=True and sub-session ID
        # Pass vector_store_ids=[whiteboard_store_id] to executor
```

**Tests to Write First**:
```python
def test_collaboration_service_init():
    """Test service initializes with dependencies"""
    
def test_execute_creates_new_session():
    """Test new collaboration session creation"""
    
def test_execute_continues_existing_session():  
    """Test resuming existing session"""
    
def test_round_robin_turn_sequence():
    """Test models called in correct order"""
    
def test_orchestrator_decision_making():
    """Test orchestrator selects next model"""
    
def test_model_turn_execution():
    """Test individual model gets whiteboard context"""
    
def test_whiteboard_context_injection():
    """Test whiteboard vector store passed via executor vector_store_ids override"""
    
def test_history_isolation():
    """Test sub-calls use disable_history_record=True and unique sub-session IDs"""
    
def test_error_handling_model_failure():
    """Test graceful handling of model failures"""
    
def test_timeout_handling():
    """Test per-step timeout enforcement"""
```

#### 3.2 Orchestration Logic
- **Round Robin**: Simple index-based rotation through models
- **Orchestrator Mode**: Use designated model to choose next participant
- **Error Recovery**: Skip failed models, continue with others
- **Cost Tracking**: Monitor token usage and API costs

### Phase 4: Tool Definition

#### 4.1 User-Facing Tool
- **File**: `mcp_the_force/tools/definitions/collaboration.py`

```python
@tool
class ChatterCollaborate(ToolSpec):
    """
    Facilitates multi-model collaboration on complex tasks.
    Models share a whiteboard where they contribute ideas and build solutions together.
    """
    model_name = "chatter_collaborate"
    description = "Enable multiple AI models to collaborate on solving complex problems."
    service_cls = CollaborationService
    adapter_class = None
    timeout = 1800  # 30 minutes

    session_id: str = Route.session(
        description="Unique identifier for the collaboration session"
    )
    objective: str = Route.adapter(
        description="The main task or problem for models to solve collaboratively"
    )
    models: List[str] = Route.adapter(
        description="List of model tools to participate (e.g., ['chat_with_gpt52', 'chat_with_gemini3_pro_preview'])"
    )
    user_input: str = Route.adapter(
        default="",
        description="Additional input or guidance for the next collaboration turn"
    )
    mode: Literal["round_robin", "orchestrator"] = Route.adapter(
        default="round_robin",
        description="Collaboration style: 'round_robin' cycles through models, 'orchestrator' uses smart routing"
    )
    max_steps: int = Route.adapter(
        default=10,
        description="Maximum number of collaboration turns"
    )
    parallel: int = Route.adapter(
        default=1,
        description="Number of models to run in parallel (1 for sequential)"
    )
```

**Tests to Write First**:
```python
def test_tool_registration():
    """Test tool registers correctly in MCP system"""
    
def test_tool_parameter_validation():
    """Test parameter validation and defaults"""
    
def test_tool_execution_flow():
    """Test tool calls service correctly"""
    
def test_tool_error_handling():
    """Test tool handles service errors gracefully"""
```

#### 4.2 Tool Registration
- **File**: `mcp_the_force/tools/definitions/__init__.py`
- **Action**: Add `from . import collaboration  # noqa: F401`

### Phase 5: Integration & Testing

#### 5.1 Critical Integration Tests  
- **File**: `tests/integration_mcp/test_collaboration_tool.py`
- **Essential Scenarios**:
  - **Whiteboard attachment verification**: Ensure models receive `file_search` (OpenAI) or `search_task_files` (others)
  - **Provider fallback testing**: OpenAI quota exceeded → HNSW works
  - **History pollution prevention**: Only meta-tool stores permanent history
  - **Vector store lease renewal**: Long collaborations don't expire stores
  - **Cost tracking and limits**: Monitor API usage per collaboration

#### 5.2 E2E Testing Strategy
- **File**: `tests/e2e_dind/test_collaboration_e2e.py`
- **Scenarios**:
  - Real API calls with rate limiting
  - Cost monitoring and limits
  - Long-running collaborations
  - Cleanup and resource management

### Phase 6: Advanced Features

#### 6.1 Parallel Execution
- Use `asyncio.gather()` for concurrent model calls
- Implement proper timeout and cancellation with `OperationManager`
- Synthesize results from parallel contributions

#### 6.2 Smart Summarization
- Integrate with existing `DescribeSessionService`
- Automatic rollover when message count exceeds threshold
- Preserve searchability while reducing token costs

#### 6.3 Cost Controls
- Track API costs per collaboration
- Implement spending limits and alerts
- Provide cost breakdowns by model

## File Structure

```
mcp_the_force/
├── types/
│   └── collaboration.py              # Core data types
├── local_services/
│   ├── collaboration_service.py      # Main orchestration logic
│   └── whiteboard_manager.py         # Vector store management
├── tools/definitions/
│   └── collaboration.py              # User-facing tool
├── utils/
│   └── message_serializer.py         # VSFile conversion utilities
└── tests/
    ├── unit/
    │   ├── test_collaboration_service.py
    │   ├── test_whiteboard_manager.py
    │   └── test_message_serializer.py
    ├── integration_mcp/
    │   └── test_collaboration_tool.py
    └── e2e_dind/
        └── test_collaboration_e2e.py
```

## Development Workflow (TDD + Integration First)

1. **Phase 1**: Fix executor passthrough (enables whole architecture)
2. **Red**: Write failing tests for each component
3. **Green**: Implement minimal code to pass tests  
4. **Integration Early**: Test vector store attachment reaches models
5. **Refactor**: Clean up and optimize
6. **E2E**: Validate full system behavior with real APIs

## Success Metrics

- [ ] Models can successfully share context via whiteboard
- [ ] No adapter modifications required
- [ ] Token budgets remain predictable
- [ ] Session history stays clean (no pollution)
- [ ] Cost controls prevent runaway spending  
- [ ] Collaboration sessions survive restarts
- [ ] Error recovery keeps sessions functional
- [ ] Performance scales to 10+ model conversations

## Risk Mitigation

- **Vector Store Limits**: Implement automatic cleanup and rollover
- **API Rate Limits**: Add exponential backoff and retry logic
- **Memory Usage**: Monitor whiteboard size and compress old content
- **Cost Explosions**: Hard limits on steps, tokens, and spending
- **Session Corruption**: Validate state transitions and rollback capability

This plan follows TDD principles by defining tests first, ensures clean integration with existing systems, and provides a robust foundation for multi-model collaboration.
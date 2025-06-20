# MCP Second-Brain Usage Examples

This document provides practical examples of using the MCP Second-Brain server based on actual testing.

## Basic Tool Usage

### 1. List Available Models
```python
result = await mcp.call_tool("list_models", {})
# Returns detailed information about all available tools and their parameters
```

### 2. Simple Analysis with Gemini Flash
```python
result = await mcp.call_tool(
    "vertex_gemini25_flash",
    instructions="What is 2+2? Be brief.",
    output_format="Just the number",
    context=[]
)
# Returns: "4"
```

### 3. Creative Generation with Temperature
```python
result = await mcp.call_tool(
    "vertex_gemini25_pro",
    instructions="Write a haiku about Python descriptors",
    output_format="Standard haiku format (5-7-5 syllables)",
    context=[],
    temperature=0.8  # Higher temperature for creativity
)
```

## Advanced Features

### 4. File Context Analysis
```python
result = await mcp.call_tool(
    "vertex_gemini25_flash",
    instructions="Summarize what the RouteDescriptor class does",
    output_format="Brief technical summary",
    context=["/path/to/descriptors.py"]
)
```

### 5. Deep Reasoning with o3
```python
result = await mcp.call_tool(
    "open_aio3_reasoning",
    instructions="Prove that for any positive integer n, the sum 1+2+3+...+n equals n(n+1)/2",
    output_format="Mathematical proof with clear steps",
    context=[],
    reasoning_effort="low"  # Can be "low", "medium", or "high"
)
```

### 6. Multi-turn Conversations
```python
# First message
result1 = await mcp.call_tool(
    "open_aio3_reasoning",
    instructions="Let's debug a Python issue. I have a function that sometimes returns None...",
    output_format="Analysis and initial thoughts",
    context=[],
    session_id="debug-session-1"
)

# Follow-up in same session
result2 = await mcp.call_tool(
    "open_aio3_reasoning",
    instructions="Good analysis! I found that user_id is a string but database keys are integers.",
    output_format="Recommended fix with code",
    context=[],
    session_id="debug-session-1"  # Same session ID continues the conversation
)
```

### 7. Vector Store Creation and Usage
```python
# Create a persistent vector store
vs_result = await mcp.call_tool(
    "create_vector_store_tool",
    files=["/path/to/src/", "/path/to/docs/"],
    name="project-knowledge-base"
)
# Returns: {"vector_store_id": "vs_...", "status": "created"}

# Use with attachments for RAG
result = await mcp.call_tool(
    "open_aigpt4_long_context",
    instructions="Find all code that handles mutable defaults",
    output_format="List each file and specific code sections",
    context=[],  # Empty context
    attachments=["/path/to/codebase/"]  # Will create vector store automatically
)
```

## Workflow Examples

### Complex Debugging Workflow
```python
# Step 1: Quick triage with Gemini Flash
triage = await mcp.call_tool(
    "flash-summary-sprinter",  # Using alias
    instructions="Identify performance bottlenecks in this React app",
    output_format="Quick list of potential issues",
    context=["/path/to/src/"]
)

# Step 2: Deep analysis with Gemini Pro
analysis = await mcp.call_tool(
    "deep-multimodal-reasoner",  # Using alias
    instructions="Deep dive into the render performance issues identified",
    output_format="Detailed analysis with optimization strategies",
    context=["/path/to/Dashboard.tsx"],
    temperature=0.2  # Lower temperature for focused analysis
)

# Step 3: If needed, escalate to o3-pro
deep_analysis = await mcp.call_tool(
    "slow-and-sure-thinker",  # Using alias
    instructions="Prove the optimization will work without side effects",
    output_format="Formal analysis with guarantees",
    context=["/path/to/Dashboard.tsx"],
    reasoning_effort="high",
    max_reasoning_tokens=100000
)
```

### RAG-Enhanced Code Review
```python
# For large codebases that exceed context limits
review = await mcp.call_tool(
    "open_aigpt4_long_context",
    instructions="Review this codebase for security vulnerabilities",
    output_format="Categorized list of issues with severity",
    context=[],  # No inline context
    attachments=["/path/to/large-project/"]  # Automatic vector store
)
```

## Parameter Routing

Each parameter is routed to the appropriate subsystem:

| Parameter | Route | Purpose | Example |
|-----------|-------|---------|---------|
| `instructions` | prompt | Main task description | `"Analyze this function"` |
| `output_format` | prompt | Expected response format | `"Brief summary"` |
| `context` | prompt | Files to inline in prompt | `["/path/to/file.py"]` |
| `temperature` | adapter | Model creativity (0-1) | `0.7` |
| `reasoning_effort` | adapter | o3/o3-pro reasoning depth | `"high"` |
| `attachments` | vector_store | Files for RAG search | `["/large/codebase/"]` |
| `session_id` | session | Conversation continuity | `"debug-123"` |

## Important Notes

1. **Always use absolute paths** in `context` and `attachments`
2. **Set appropriate timeouts** for o3-pro (can take 10-30 minutes)
3. **Context limits**: 
   - Gemini models: ~1M tokens
   - o3/o3-pro: ~200k tokens
   - GPT-4.1: ~1M tokens
4. **Session support** only available for OpenAI models
5. **Vector stores** are automatically cleaned up after use
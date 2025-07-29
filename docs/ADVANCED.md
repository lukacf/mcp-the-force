# Advanced Integration Guide

This document contains advanced usage patterns and integration strategies for power users of the MCP The-Force server.

## Claude Integration Strategy

This guide outlines how Claude should optimally use the The Force MCP server, leveraging parallel execution capabilities for maximum effectiveness.

### Core Architecture: Three-Phase Intelligence Gathering

When The Force MCP is available, Claude operates as an orchestrator of specialized AI models, using a three-phase approach:

#### Phase 1: Broad Surface Scan (5-10s)
Launch 2-3 cheap, fast queries to map the problem space:
```python
Task 1: gemini25_flash - "What are the main issues here?"
Task 2: gemini25_flash - "What solutions have worked for similar problems?"
Task 3: gpt4_1 - "Find all related code patterns"
```

#### Phase 2: Deep Focus (30-60s)
Based on Phase 1, pursue the most promising angles:
```python
# Pick top 2 insights from Phase 1
Task 1: gemini25_pro - "Deep dive into [specific issue from Phase 1]"
Task 2: o3 (new session) - "Trace execution for [hypothesis from Phase 1]"
```

#### Phase 3: Synthesis & Arbitration (10s)
Reconcile findings:
```python
gemini25_flash - "Reconcile these analyses: [all findings]. Highlight conflicts, suggest resolution."
```

### Parallel Execution Rules

#### Concurrency Limits
- Maximum 3 heavy models simultaneously (respect rate limits)
- Stagger launches by 100ms to avoid burst throttling
- On 429 errors: exponential backoff, queue remaining

#### Session Hygiene
```python
# CORRECT: One session per hypothesis/topic
session_id="debug-jwt-race-2024-06-22"    # Hypothesis 1
session_id="debug-jwt-timing-2024-06-22"  # Hypothesis 2

# WRONG: Same session for different hypotheses
session_id="debug-jwt"  # Contaminates reasoning paths
```

#### Context Optimization
```python
# First call: Automatic vector store creation for large contexts
chat_with_gpt4_1(
    context=["/large/codebase"],  # Auto-creates vector store if > 85% of context window
    session_id="analysis-main"
)

# Subsequent calls: Reference same session for efficient processing
chat_with_gemini25_pro(
    context=["/specific/files"],  # Can add new context
    session_id="analysis-main"  # Reuses vector store from session
)
```

### Model Selection Strategies

#### For Debugging
```python
# Primary: Fast hypothesis generation
gemini25_flash("What could cause this error?")

# Secondary: Deep reasoning on top hypothesis
o3("Trace execution of [specific hypothesis]")

# Validation: Different perspective
gemini25_pro("What did we miss in this analysis?")
```

#### For Architecture Review
```python
# Overview: Large context for patterns
gpt4_1(context=["/entire/codebase"], "Find architectural inconsistencies")

# Deep dive: Specific subsystems
gemini25_pro("Analyze the data layer for ACID compliance issues")

# Research: External best practices
research_with_o3_deep_research("Industry standards for [identified patterns]")
```

#### For Code Generation
```python
# Planning: Structure and approach
o3("Design API structure for [requirements]")

# Implementation: Detailed coding
gemini25_pro("Implement [design] with proper error handling")

# Review: Quality assurance
gpt4_1("Review implementation for security and performance issues")
```

### Error Handling Patterns

#### Graceful Degradation
```python
try:
    # Preferred: Multiple models for robustness
    results = await parallel_execution([
        ("gemini25_pro", analysis_prompt),
        ("o3", reasoning_prompt),
        ("gpt4_1", validation_prompt)
    ])
except TimeoutError:
    # Fallback: Single fast model
    result = await chat_with_gemini25_flash(fallback_prompt)
```

#### Rate Limit Management
```python
# Stagger execution to avoid burst limits
for i, task in enumerate(tasks):
    await asyncio.sleep(i * 0.1)  # 100ms stagger
    launch_task(task)
```

#### Context Window Management
```python
# Large codebase strategy (handled automatically)
if codebase_size > (model_context_window * 0.85):
    # Server automatically creates vector store
    # No special handling needed - just use context
    pass
else:
    # Server inlines files directly
    # Again, no special handling needed
    pass
```

### Performance Optimization

#### Smart Caching
```python
# Reuse sessions for related queries
session_id = f"project-analysis-{date.today()}"

# First analysis creates memory
chat_with_gpt4_1(
    instructions="Analyze architecture",
    context=["/src"],
    session_id=session_id
)

# Follow-up queries leverage memory
chat_with_gemini25_pro(
    instructions="Focus on security aspects",
    context=[],  # Relies on session memory
    session_id=session_id
)
```

#### Resource Management
```python
# Monitor token usage
response = await call_tool("list_models")
for model in response:
    if model["context_remaining"] < 0.2:
        # Switch to fresh session
        session_id = generate_new_session_id()
```

### Advanced Workflows

#### Multi-Model Code Review
```python
# 1. Overview (fast)
overview = await chat_with_gemini25_flash(
    "Quick security scan of this PR",
    context=pr_files
)

# 2. Deep analysis (parallel)
tasks = [
    ("gemini25_pro", "Detailed security analysis"),
    ("o3", "Logic flow verification"),
    ("gpt4_1", "Performance impact assessment")
]
analyses = await execute_parallel(tasks)

# 3. Synthesis
final_review = await chat_with_gemini25_flash(
    f"Synthesize these reviews: {analyses}",
    structured_output_schema=review_schema
)
```

#### Research-Driven Development
```python
# 1. Research best practices
best_practices = await research_with_o4_mini_deep_research(
    "Current best practices for [technology]",
    session_id="research-session"
)

# 2. Apply to current codebase
implementation = await chat_with_o3(
    f"Apply these practices to our code: {best_practices}",
    context=["/src"],
    session_id="implementation-session"
)

# 3. Validate approach
validation = await chat_with_gemini25_pro(
    "Review implementation for compliance with researched practices",
    context=[implementation],
    session_id="validation-session"
)
```

#### Iterative Problem Solving
```python
max_iterations = 3
for iteration in range(max_iterations):
    # Generate hypothesis
    hypothesis = await chat_with_o3(
        f"Iteration {iteration}: Generate testable hypothesis for bug",
        session_id=f"debug-iteration-{iteration}"
    )
    
    # Test hypothesis
    test_result = await chat_with_gemini25_pro(
        f"Test this hypothesis: {hypothesis}",
        context=["/test", "/src"],
        session_id=f"test-iteration-{iteration}"
    )
    
    if "confirmed" in test_result.lower():
        break
    
    # Refine for next iteration
    await chat_with_gemini25_flash(
        f"Refine hypothesis based on: {test_result}",
        session_id=f"refine-iteration-{iteration}"
    )
```

### Cost Optimization

#### Model Selection by Cost
```python
# High-priority, time-sensitive
if priority == "urgent":
    primary_model = "gemini25_flash"  # Fastest
    fallback_model = "gemini25_pro"   # If quality needed

# Deep analysis, quality critical
elif task_type == "architecture":
    primary_model = "o3_pro"          # Best reasoning
    fallback_model = "o3"             # Faster alternative

# Large context processing
elif context_size > 500_kb:
    primary_model = "gpt4_1"          # Best RAG
    fallback_model = "gemini25_pro"   # Large context
```

#### Session Reuse Strategy
```python
# Group related queries in same session
session_themes = {
    "security-review": ["security", "auth", "crypto"],
    "performance-analysis": ["perf", "optimization", "bottleneck"],
    "architecture-planning": ["design", "structure", "patterns"]
}

def get_session_id(query):
    for theme, keywords in session_themes.items():
        if any(keyword in query.lower() for keyword in keywords):
            return f"{theme}-{date.today()}"
    return f"general-{uuid4()}"
```

### Monitoring and Debugging

#### Performance Tracking
```python
import time

async def timed_model_call(model, prompt, **kwargs):
    start = time.time()
    result = await call_tool(model, prompt, **kwargs)
    duration = time.time() - start
    
    logger.info(f"{model}: {duration:.2f}s for {len(prompt)} chars")
    return result
```

#### Error Pattern Recognition
```python
# Common failure patterns
error_patterns = {
    "rate_limit": "429 Too Many Requests",
    "context_overflow": "context length exceeded",
    "auth_failure": "authentication failed",
    "timeout": "request timeout"
}

def diagnose_error(error_msg):
    for pattern, signature in error_patterns.items():
        if signature in error_msg:
            return f"Known issue: {pattern}"
    return "Unknown error pattern"
```

### Best Practices Summary

1. **Start Fast, Go Deep**: Use gemini25_flash for initial exploration, then targeted deep models
2. **Parallel Everything**: Launch multiple models simultaneously when possible
3. **Session Hygiene**: One session per logical thread of reasoning
4. **Smart Fallbacks**: Always have a faster/cheaper model as backup
5. **Monitor Resources**: Track token usage and session memory
6. **Cache Aggressively**: Reuse sessions for related queries
7. **Synthesize Results**: Use fast models to reconcile multiple analyses
8. **Profile Performance**: Measure and optimize model selection
9. **Handle Failures Gracefully**: Expect rate limits and context overflows
10. **Document Decisions**: Use project history to capture reasoning patterns
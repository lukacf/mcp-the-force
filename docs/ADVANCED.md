# Advanced Integration Guide

This document contains advanced usage patterns and integration strategies for power users of the MCP The-Force server.

## Claude Integration Strategy

This guide outlines how Claude should optimally use the The Force MCP server, leveraging parallel execution capabilities for maximum effectiveness.

### Core Architecture: Three-Phase Intelligence Gathering

When The Force MCP is available, Claude operates as an orchestrator of specialized AI models, using a three-phase approach:

#### Phase 1: Broad Surface Scan (5-10s)
Launch 2-3 cheap, fast queries to map the problem space:
```python
# Use consult_with for quick hypothesis generation
consult_with(model="gemini-3-flash-preview", question="What are the main issues here?", ...)
consult_with(model="gemini-3-flash-preview", question="What solutions have worked for similar problems?", ...)
```

#### Phase 2: Deep Focus (30-60s)
Based on Phase 1, pursue the most promising angles:
```python
# Use work_with for deep investigation with file access
work_with(agent="claude-sonnet-4-5", task="Deep dive into [specific issue from Phase 1]", reasoning_effort="high", ...)
work_with(agent="gpt-5.2-pro", task="Trace execution for [hypothesis from Phase 1]", reasoning_effort="high", ...)
```

#### Phase 3: Synthesis & Arbitration (10s)
Reconcile findings:
```python
consult_with(model="gemini-3-flash-preview", question="Reconcile these analyses: [all findings]. Highlight conflicts, suggest resolution.", ...)
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

#### Cross-Tool Session Continuity
```python
# Sessions work across work_with and consult_with
work_with(
    agent="claude-sonnet-4-5",
    task="Analyze the auth module",
    session_id="analysis-main"
)

# Continue with consult_with - same session maintains context
consult_with(
    model="gpt-5.2-pro",
    question="Based on our analysis, what's the best approach?",
    output_format="markdown",
    session_id="analysis-main"  # Reuses context from work_with
)
```

### Model Selection Strategies

#### For Debugging
```python
# Primary: Fast hypothesis generation (consult_with)
consult_with(model="gemini-3-flash-preview", question="What could cause this error?", ...)

# Secondary: Deep reasoning with file access (work_with)
work_with(agent="claude-sonnet-4-5", task="Trace execution of [specific hypothesis]", reasoning_effort="high", ...)

# Validation: Different perspective (consult_with)
consult_with(model="gpt-5.2-pro", question="What did we miss in this analysis?", ...)
```

#### For Architecture Review
```python
# Overview: Use work_with for comprehensive file access
work_with(agent="claude-sonnet-4-5", task="Find architectural inconsistencies", session_id="arch-review")

# Deep dive: Specific subsystems
work_with(agent="gemini-3-pro-preview", task="Analyze the data layer for ACID compliance issues", ...)

# Research: External best practices (async)
research_with_o3_deep_research(instructions="Industry standards for [identified patterns]", ...)
```

#### For Code Generation
```python
# Planning: Structure and approach
work_with(agent="gpt-5.2-pro", task="Design API structure for [requirements]", role="planner", ...)

# Implementation: Detailed coding
work_with(agent="claude-sonnet-4-5", task="Implement [design] with proper error handling", ...)

# Review: Quality assurance
work_with(agent="claude-sonnet-4-5", task="Review implementation for security and performance issues", role="codereviewer", ...)
```

### Error Handling Patterns

#### Graceful Degradation
```python
try:
    # Preferred: work_with for comprehensive analysis
    work_with(agent="claude-sonnet-4-5", task=analysis_task, reasoning_effort="high", ...)
except TimeoutError:
    # Fallback: Quick consult_with
    consult_with(model="gemini-3-flash-preview", question=fallback_prompt, ...)
```

#### Rate Limit Management
```python
# Stagger execution to avoid burst limits
for i, task in enumerate(tasks):
    await asyncio.sleep(i * 0.1)  # 100ms stagger
    launch_task(task)
```

### Performance Optimization

#### Smart Caching
```python
# Reuse sessions for related queries
session_id = f"project-analysis-{date.today()}"

# First analysis with work_with creates memory
work_with(
    agent="claude-sonnet-4-5",
    task="Analyze architecture",
    session_id=session_id
)

# Follow-up queries leverage memory
consult_with(
    model="gpt-5.2-pro",
    question="Focus on security aspects of what we found",
    output_format="markdown",
    session_id=session_id  # Shares context
)
```

### Advanced Workflows

#### Multi-Model Collaboration (GroupThink)
```python
group_think(
    session_id="refactor-auth-2025-11-21",
    objective="Redesign auth service for zero-downtime rotations",
    models=["chat_with_gpt52_pro", "chat_with_gemini3_pro_preview", "chat_with_claude45_opus", "chat_with_grok41"],
    output_format="Design doc + migration steps + rollback plan",
    discussion_turns=6,
    validation_rounds=2,
    context=["/abs/path/to/auth-service"],
    priority_context=["/abs/path/to/auth-service/docs/security.md"]
)
```
- Keep `session_id` stable to continue the same panel across turns.
- Choose a large-context `synthesis_model` (default: `chat_with_gemini3_pro_preview`) for the final merge.
- Use `mode="round_robin"` (current default) to ensure every model contributes.
- **Note**: GroupThink uses internal `chat_with_*` tool names in the `models` parameter.

#### Multi-Model Code Review
```python
# 1. Overview with work_with (fast)
work_with(
    agent="gemini-3-flash-preview",
    task="Quick security scan of this PR",
    session_id="pr-review"
)

# 2. Deep analysis with different perspectives
work_with(agent="claude-sonnet-4-5", task="Detailed security analysis", session_id="pr-review-security")
work_with(agent="gpt-5.2-pro", task="Logic flow verification", session_id="pr-review-logic")

# 3. Synthesis
consult_with(
    model="gemini-3-pro-preview",
    question="Synthesize these reviews into a final assessment",
    output_format="structured review with severity ratings",
    session_id="pr-review-final"
)
```

#### Research-Driven Development
```python
# 1. Research best practices (async)
research_with_o4_mini_deep_research(
    instructions="Current best practices for [technology]",
    session_id="research-session"
)

# 2. Apply to current codebase
work_with(
    agent="gpt-5.2-pro",
    task="Apply these practices to our code: [best_practices]",
    session_id="implementation-session"
)

# 3. Validate approach
work_with(
    agent="claude-sonnet-4-5",
    task="Review implementation for compliance with researched practices",
    session_id="validation-session",
    role="codereviewer"
)
```

#### Iterative Problem Solving
```python
max_iterations = 3
for iteration in range(max_iterations):
    # Generate hypothesis
    work_with(
        agent="gpt-5.2-pro",
        task=f"Iteration {iteration}: Generate testable hypothesis for bug",
        session_id=f"debug-iteration-{iteration}",
        reasoning_effort="high"
    )

    # Test hypothesis
    work_with(
        agent="claude-sonnet-4-5",
        task=f"Test this hypothesis: {hypothesis}",
        session_id=f"test-iteration-{iteration}"
    )

    if confirmed:
        break

    # Refine for next iteration
    consult_with(
        model="gemini-3-flash-preview",
        question=f"Refine hypothesis based on: {test_result}",
        output_format="refined hypothesis",
        session_id=f"refine-iteration-{iteration}"
    )
```

### Cost Optimization

#### Model Selection by Cost
```python
# High-priority, time-sensitive
if priority == "urgent":
    # Use consult_with for quick opinions
    consult_with(model="gemini-3-flash-preview", ...)

# Deep analysis, quality critical
elif task_type == "architecture":
    # Use work_with with high reasoning
    work_with(agent="gpt-5.2-pro", reasoning_effort="high", ...)

# Large context processing - work_with has native file access
elif needs_file_access:
    work_with(agent="claude-sonnet-4-5", ...)
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

1. **Choose the Right Tool**: `work_with` for action (file access), `consult_with` for advice
2. **Start Fast, Go Deep**: Use gemini-3-flash-preview for initial exploration, then targeted deep models
3. **Parallel Everything**: Launch multiple models simultaneously when possible
4. **Session Hygiene**: One session per logical thread of reasoning
5. **Cross-Tool Sessions**: Same session_id works across work_with and consult_with
6. **Smart Fallbacks**: Always have a faster/cheaper model as backup
7. **Reasoning Effort**: Use `high`/`xhigh` only for complex problems
8. **Monitor Resources**: Track token usage and session memory
9. **Handle Failures Gracefully**: Expect rate limits and context overflows
10. **Document Decisions**: Use project history to capture reasoning patterns

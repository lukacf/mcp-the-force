# Common Patterns - Copy-Paste Ready

## Basic Patterns

### Simple Analysis
```
chat_with_gpt52_pro(
    instructions="Analyze this codebase for potential issues",
    context=["/absolute/path/to/src"],
    session_id="analysis-YYYY-MM-DD",
    output_format="Markdown report"
)
```

### Code Review
```
chat_with_gemini3_pro_preview(
    instructions="Review this code for security vulnerabilities and performance issues",
    context=["/absolute/path/to/file.py"],
    priority_context=["/absolute/path/to/security_config.py"],
    session_id="code-review-YYYY-MM-DD",
    output_format="List of issues with severity and recommendations"
)
```

### Quick Question
```
chat_with_gemini25_flash(
    instructions="What does this function do?",
    context=["/absolute/path/to/module.py"],
    session_id="quick-q-YYYY-MM-DD",
    output_format="Plain text explanation"
)
```

## Session Continuity

### Multi-Turn Conversation
```
# Turn 1: Initial analysis
chat_with_gpt52_pro(
    instructions="Analyze the authentication flow",
    context=["/src/auth"],
    session_id="auth-deep-dive"
)

# Turn 2: Follow-up (same session)
chat_with_gpt52_pro(
    instructions="Now focus on the JWT validation logic",
    session_id="auth-deep-dive"  # Remembers Turn 1
)

# Turn 3: Switch models (same session still works)
chat_with_gemini3_pro_preview(
    instructions="Summarize what we found",
    session_id="auth-deep-dive"  # Works across models
)
```

## Structured Output

### JSON Response
```
chat_with_gpt52_pro(
    instructions="Find all API endpoints in this codebase",
    context=["/src"],
    session_id="api-analysis",
    output_format="JSON",
    structured_output_schema={
        "type": "object",
        "properties": {
            "endpoints": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "method": {"type": "string"},
                        "handler": {"type": "string"}
                    },
                    "required": ["path", "method", "handler"],
                    "additionalProperties": false
                }
            }
        },
        "required": ["endpoints"],
        "additionalProperties": false
    }
)
```

### Severity Classification
```
chat_with_gpt41(
    instructions="Classify these issues by severity",
    context=["/analysis-results.txt"],
    session_id="classify",
    structured_output_schema={
        "type": "object",
        "properties": {
            "critical": {"type": "array", "items": {"type": "string"}},
            "high": {"type": "array", "items": {"type": "string"}},
            "medium": {"type": "array", "items": {"type": "string"}},
            "low": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["critical", "high", "medium", "low"],
        "additionalProperties": false
    }
)
```

## Three-Phase Analysis

### Phase 1: Surface Scan (parallel)
```
# Launch in parallel
chat_with_gemini25_flash(
    instructions="What are the main architectural patterns?",
    context=["/src"],
    session_id="arch-scan-patterns"
)

chat_with_gemini25_flash(
    instructions="What are potential performance bottlenecks?",
    context=["/src"],
    session_id="arch-scan-perf"
)

chat_with_gemini25_flash(
    instructions="What security concerns do you see?",
    context=["/src"],
    session_id="arch-scan-security"
)
```

### Phase 2: Deep Dive
```
chat_with_gpt52_pro(
    instructions="Deep analysis of [specific finding from Phase 1]",
    context=["/src/relevant/module"],
    session_id="arch-deep-dive",
    reasoning_effort="high"
)
```

### Phase 3: Synthesis
```
chat_with_gemini25_flash(
    instructions="Synthesize these findings into a cohesive report: [Phase 1 + Phase 2 results]",
    session_id="arch-synthesis",
    output_format="Executive summary with key findings and recommendations"
)
```

## GroupThink Collaboration

### Design Review Panel
```
group_think(
    session_id="design-review-YYYY-MM-DD",
    objective="Review and improve the proposed API design",
    models=[
        "chat_with_gpt52_pro",
        "chat_with_gemini3_pro_preview",
        "chat_with_claude45_opus"
    ],
    output_format="Design document with: Overview, Endpoints, Data Models, Security Considerations, Migration Plan",
    context=["/src/api"],
    priority_context=["/docs/api-spec.yaml"],
    discussion_turns=6,
    validation_rounds=2
)
```

### Code Refactoring Panel
```
group_think(
    session_id="refactor-panel",
    objective="Plan the refactoring of the legacy authentication module",
    models=[
        "chat_with_gpt52_pro",
        "chat_with_gemini3_pro_preview",
        "chat_with_gpt41"
    ],
    output_format="Refactoring plan with: Current issues, Target architecture, Step-by-step migration, Risk assessment",
    context=["/src/auth"],
    discussion_turns=8,
    validation_rounds=2
)
```

### Continue Existing Panel
```
group_think(
    session_id="design-review-YYYY-MM-DD",  # Same ID as before
    user_input="Focus specifically on the authentication flow and OAuth integration",
    models=[
        "chat_with_gpt52_pro",
        "chat_with_gemini3_pro_preview",
        "chat_with_claude45_opus"
    ],
    objective="...",
    output_format="..."
)
```

## Async Jobs

### Long-Running Research
```
# Start async research
job = start_job(
    target_tool="research_with_o3_deep_research",
    args={
        "instructions": "Research best practices for implementing OAuth 2.0 with PKCE",
        "session_id": "oauth-research",
        "output_format": "Comprehensive guide with implementation steps"
    },
    max_runtime_s=3600
)

# ... do other work ...

# Check status
result = poll_job(job_id=job["job_id"])
# result.status: "pending" | "running" | "completed" | "failed"
```

### Large Token Count
```
job = start_job(
    target_tool="count_project_tokens",
    args={
        "items": ["/large/monorepo"],
        "top_n": 20
    }
)

result = poll_job(job_id=job["job_id"])
```

## History Search

### Find Past Decisions
```
search_project_history(
    query="authentication design decisions; JWT vs session tokens",
    max_results=20,
    store_types=["conversation", "commit"]
)
```

### Search Multiple Topics
```
search_project_history(
    query="database migration; schema changes; performance optimization",
    max_results=30
)
```

## Error Handling Patterns

### Fallback Chain
```
# Try primary model
try:
    chat_with_gpt52_pro(...)
except:
    # Fallback to faster model
    chat_with_gemini3_pro_preview(...)
```

### Context Overflow Recovery
```
# Check token count first
count_project_tokens(items=["/src"])

# If too large, use priority_context for essentials
chat_with_gemini3_pro_preview(
    instructions="...",
    context=["/src"],  # Will auto-split to vector store
    priority_context=["/src/critical_module.py"]  # Always inline
)
```

## Debugging Patterns

### Hypothesis Testing
```
# Generate hypotheses
chat_with_gemini25_flash(
    instructions="What could cause this error: [error message]?",
    context=["/src"],
    session_id="debug-hypothesis"
)

# Deep trace on top hypothesis
chat_with_gpt52_pro(
    instructions="Trace execution path for hypothesis: [hypothesis]",
    context=["/src"],
    session_id="debug-trace",
    reasoning_effort="high"
)

# Validate fix
chat_with_gemini3_pro_preview(
    instructions="Review this fix for unintended side effects",
    context=["/src/fix.py"],
    session_id="debug-validate"
)
```

## Research Patterns

### Deep Research
```
research_with_o3_deep_research(
    instructions="Comprehensive analysis of modern authentication patterns for microservices",
    session_id="auth-research-deep",
    output_format="Research report with: Current best practices, Comparison of approaches, Implementation recommendations, References"
)
```

### Quick Research
```
research_with_o4_mini_deep_research(
    instructions="Quick overview of GraphQL subscription patterns",
    session_id="graphql-research",
    output_format="Summary with key points and top 3 recommendations"
)
```

## Session Management

### List Recent Sessions
```
list_sessions(limit=10, include_summary=true)
```

### Get Session Summary
```
describe_session(
    session_id="auth-analysis",
    extra_instructions="Focus on the key decisions made"
)
```

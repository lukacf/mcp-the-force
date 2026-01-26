# Common Patterns - Copy-Paste Ready

## Basic Patterns

### Code Investigation (work_with)
```
work_with(
    agent="claude-sonnet-4-5",
    task="Analyze this codebase for potential issues",
    session_id="analysis-YYYY-MM-DD"
)
```

### Code Review (work_with)
```
work_with(
    agent="claude-sonnet-4-5",
    task="Review this code for security vulnerabilities and performance issues",
    session_id="code-review-YYYY-MM-DD",
    role="codereviewer"
)
```

### Quick Question (consult_with)
```
consult_with(
    model="gemini-3-flash-preview",
    question="What does this function do? [paste code]",
    output_format="Plain text explanation",
    session_id="quick-q-YYYY-MM-DD"
)
```

### Deep Analysis (consult_with)
```
consult_with(
    model="gpt-5.2-pro",
    question="Analyze this architecture for potential issues: [description]",
    output_format="Markdown report",
    session_id="analysis-YYYY-MM-DD"
)
```

## Session Continuity

### Cross-Tool Conversation
```
# Turn 1: Agentic exploration
work_with(
    agent="claude-sonnet-4-5",
    task="Analyze the authentication flow in src/auth",
    session_id="auth-deep-dive"
)

# Turn 2: Quick opinion (same session)
consult_with(
    model="gpt-5.2-pro",
    question="Based on our analysis, what's the best approach to fix the issues?",
    output_format="markdown",
    session_id="auth-deep-dive"  # Remembers Turn 1
)

# Turn 3: Implement the fix
work_with(
    agent="claude-sonnet-4-5",
    task="Implement the recommended fix",
    session_id="auth-deep-dive"  # Full context preserved
)
```

### Multi-Turn with Same Tool
```
# Turn 1: Initial analysis
work_with(
    agent="claude-sonnet-4-5",
    task="Analyze the JWT validation logic",
    session_id="jwt-analysis"
)

# Turn 2: Follow-up
work_with(
    agent="claude-sonnet-4-5",
    task="Now focus on the token refresh mechanism",
    session_id="jwt-analysis"  # Remembers Turn 1
)

# Turn 3: Different model, same session
work_with(
    agent="gemini-3-pro-preview",
    task="Summarize what we found",
    session_id="jwt-analysis"  # Works across models
)
```

## Structured Output (consult_with)

### JSON Response
```
consult_with(
    model="gpt-5.2-pro",
    question="List all the API endpoints in this description: [paste route definitions]",
    output_format="JSON with schema: {endpoints: [{path: string, method: string, handler: string}]}",
    session_id="api-analysis"
)
```

### Classification
```
consult_with(
    model="gpt-5.2",
    question="Classify these issues by severity: [paste issues]",
    output_format="JSON with schema: {critical: string[], high: string[], medium: string[], low: string[]}",
    session_id="classify"
)
```

## Three-Phase Analysis

### Phase 1: Surface Scan (parallel consult_with)
```
# Launch in parallel - fast hypothesis generation
consult_with(
    model="gemini-3-flash-preview",
    question="What are the main architectural patterns in this code? [paste overview]",
    output_format="bullet list",
    session_id="arch-scan-patterns"
)

consult_with(
    model="gemini-3-flash-preview",
    question="What are potential performance bottlenecks? [paste code]",
    output_format="bullet list",
    session_id="arch-scan-perf"
)

consult_with(
    model="gemini-3-flash-preview",
    question="What security concerns do you see? [paste code]",
    output_format="bullet list",
    session_id="arch-scan-security"
)
```

### Phase 2: Deep Dive (work_with)
```
work_with(
    agent="claude-sonnet-4-5",
    task="Deep analysis of [specific finding from Phase 1]. Investigate the root cause and propose fixes.",
    session_id="arch-deep-dive",
    reasoning_effort="high"
)
```

### Phase 3: Synthesis (consult_with)
```
consult_with(
    model="gemini-3-pro-preview",
    question="Synthesize these findings into a cohesive report: [Phase 1 + Phase 2 results]",
    output_format="Executive summary with key findings and recommendations",
    session_id="arch-synthesis"
)
```

## GroupThink Collaboration

Note: GroupThink uses internal `chat_with_*` tool names.

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

## Debugging Patterns

### Hypothesis Testing
```
# Generate hypotheses (fast)
consult_with(
    model="gemini-3-flash-preview",
    question="What could cause this error: [error message]?",
    output_format="bullet list of hypotheses",
    session_id="debug-hypothesis"
)

# Deep investigation (agentic)
work_with(
    agent="claude-sonnet-4-5",
    task="Investigate hypothesis: [top hypothesis]. Find the root cause and fix it.",
    session_id="debug-hypothesis",  # Same session for context
    reasoning_effort="high"
)

# Validate fix (opinion)
consult_with(
    model="gpt-5.2-pro",
    question="Review this fix for unintended side effects: [fix summary]",
    output_format="markdown with concerns",
    session_id="debug-hypothesis"
)
```

### Race Condition Debugging
```
work_with(
    agent="gpt-5.2-pro",
    task="Analyze potential race conditions in the concurrent upload handler",
    session_id="race-debug",
    reasoning_effort="xhigh"  # Maximum reasoning for complex concurrency
)
```

## Research Patterns

### Deep Research (async)
```
research_with_o3_deep_research(
    instructions="Comprehensive analysis of modern authentication patterns for microservices",
    session_id="auth-research-deep",
    output_format="Research report with: Current best practices, Comparison of approaches, Implementation recommendations, References"
)
```

### Quick Research (async)
```
research_with_o4_mini_deep_research(
    instructions="Quick overview of GraphQL subscription patterns",
    session_id="graphql-research",
    output_format="Summary with key points and top 3 recommendations"
)
```

### Live Context (Grok)
```
consult_with(
    model="grok-4.1",
    question="What's the current sentiment about [technology] on Twitter?",
    output_format="summary with examples",
    session_id="social-research"
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

## Reasoning Effort Patterns

### Simple Task (low)
```
work_with(
    agent="claude-sonnet-4-5",
    task="Add a log statement to track API calls",
    session_id="quick-fix",
    reasoning_effort="low"
)
```

### Standard Task (medium - default)
```
work_with(
    agent="claude-sonnet-4-5",
    task="Implement input validation for the user registration form",
    session_id="validation-impl"
    # reasoning_effort defaults to "medium"
)
```

### Complex Problem (high)
```
work_with(
    agent="gpt-5.2-pro",
    task="Debug the intermittent timeout in the payment processing flow",
    session_id="payment-debug",
    reasoning_effort="high"
)
```

### Hardest Problems (xhigh)
```
work_with(
    agent="gpt-5.2-pro",
    task="Design and implement a distributed rate limiting system",
    session_id="rate-limit-design",
    reasoning_effort="xhigh"
)
```

## Role-Based Patterns

### Planner Role
```
work_with(
    agent="gpt-5.2-pro",
    task="Create a detailed implementation plan for migrating to microservices",
    session_id="migration-plan",
    role="planner"
)
```

### Code Reviewer Role
```
work_with(
    agent="claude-sonnet-4-5",
    task="Review the changes in the auth module for security issues",
    session_id="security-review",
    role="codereviewer"
)
```

## Combining Tools Effectively

### Investigation → Opinion → Action
```
# Step 1: Investigate (agentic)
work_with(
    agent="claude-sonnet-4-5",
    task="Find all places where user input is not sanitized",
    session_id="security-audit"
)

# Step 2: Get opinion on priorities (advisory)
consult_with(
    model="gpt-5.2-pro",
    question="Given these unsanitized inputs, which should we fix first?",
    output_format="prioritized list",
    session_id="security-audit"
)

# Step 3: Fix highest priority (agentic)
work_with(
    agent="claude-sonnet-4-5",
    task="Fix the highest priority sanitization issue we identified",
    session_id="security-audit"
)
```

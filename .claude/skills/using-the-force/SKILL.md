---
name: using-the-force
description: |
  Comprehensive guide for using The Force MCP server - a unified interface to 11 AI models
  (OpenAI, Google, Anthropic, xAI) with intelligent context management, project memory, and
  multi-model collaboration. This skill should be used when working with The Force MCP tools,
  selecting appropriate AI models for tasks, managing context and sessions, using GroupThink
  for multi-model collaboration, or optimizing AI-assisted workflows.
---

# Using The Force MCP Server

The Force provides unified access to 11 cutting-edge AI models through a single consistent interface with intelligent context management, long-term project memory, and multi-model collaboration capabilities.

## Two Primary Tools

The Force offers two ways to interact with AI models:

| Tool | Purpose | Model Access |
|------|---------|--------------|
| **`work_with`** | Agentic tasks - the AI can read files, run commands, take action | CLI agents (Claude Code, Gemini CLI, Codex CLI) |
| **`consult_with`** | Advisory questions - quick opinions without file access | API models (internal chat_with_* tools) |

**When to use which:**
- Use `work_with` when you need the AI to explore code, make changes, or take autonomous action
- Use `consult_with` for quick questions, analysis, or second opinions without file access

## Quick Reference: Model Selection

For 90% of work, use these models:

| Need | Model | Tool | Why |
|------|-------|------|-----|
| **Code changes** | `claude-sonnet-4-5` | `work_with` | Best coding via Claude Code CLI |
| **Quick analysis** | `gemini-3-pro-preview` | `consult_with` | Fast, 1M context, great reasoning |
| **Deep reasoning** | `gpt-5.2-pro` | `consult_with` | Smartest reasoning, best at search |

### Full Model Roster

| Model | Context | Speed | Best For | work_with | consult_with |
|-------|---------|-------|----------|-----------|--------------|
| **OpenAI** |
| `gpt-5.2-pro` | 400k | Medium | Complex reasoning, code generation, search | via Codex | Yes |
| `gpt-5.2` | 272k | Medium | General purpose, balanced | via Codex | Yes |
| `gpt-5.1-codex-max` | 272k | Medium | Elite coding with xhigh reasoning | via Codex | Yes |
| `gpt-4.1` | 1M | Fast | Large docs, RAG, low hallucination | via Codex | Yes |
| **Google** |
| `gemini-3-pro-preview` | 1M | Medium | Giant code synthesis, design reviews | via Gemini CLI | Yes |
| `gemini-3-flash-preview` | 1M | Very fast | Quick summaries, extraction, triage | via Gemini CLI | Yes |
| **Anthropic** |
| `claude-sonnet-4-5` | 1M | Fast | Latest Claude, excellent coding | via Claude Code | Yes |
| `claude-opus-4-5` | 200k | Slow | Deep extended thinking, premium quality | via Claude Code | Yes |
| **xAI** |
| `grok-4.1` | ~2M | Medium | Massive context, Live Search (X/Twitter) | No | Yes |
| **Research** |
| `o3-deep-research` | 200k | 10-60 min | Exhaustive research with citations | No | Special tool |
| `o4-mini-deep-research` | 200k | 2-10 min | Quick research reconnaissance | No | Special tool |

## Using work_with (Agentic Tasks)

The `work_with` tool spawns CLI agents that can autonomously explore code and take action.

```
work_with(
    agent="claude-sonnet-4-5",  # Model name (resolves to CLI)
    task="Refactor the auth module to use JWT",
    session_id="auth-refactor-2024",
    role="default",             # default, planner, codereviewer
    reasoning_effort="medium"   # low, medium, high, xhigh
)
```

**Key parameters:**

| Parameter | Description | Default |
|-----------|-------------|---------|
| `agent` | Model name (e.g., `gpt-5.2`, `claude-sonnet-4-5`, `gemini-3-pro-preview`) | Required |
| `task` | The task for the agent | Required |
| `session_id` | Conversation identifier (reuse to continue) | Required |
| `role` | System prompt role (default, planner, codereviewer) | `default` |
| `reasoning_effort` | Reasoning depth (low/medium/high/xhigh) | `medium` |

**Reasoning effort levels:**

| Level | Use Case | Supported By |
|-------|----------|--------------|
| `low` | Quick tasks, simple questions | All models |
| `medium` | Balanced (default) | All models |
| `high` | Complex analysis, difficult bugs | All models |
| `xhigh` | Maximum depth | GPT-5.2 Pro, GPT-5.1 Codex Max |

**Example workflow:**
```
# Start an investigation
work_with(
    agent="claude-sonnet-4-5",
    task="Find and analyze all authentication code",
    session_id="auth-audit"
)

# Continue with the same session
work_with(
    agent="claude-sonnet-4-5",
    task="Now implement rate limiting on login endpoints",
    session_id="auth-audit"  # Same session = remembers context
)

# Switch to a different model, same conversation context
work_with(
    agent="gpt-5.2",
    task="Review what Claude did and suggest improvements",
    session_id="auth-audit"
)
```

## Using consult_with (Quick Opinions)

The `consult_with` tool provides quick API access to models for analysis and opinions.

```
consult_with(
    model="gemini-3-pro-preview",
    question="What's the best approach for implementing rate limiting?",
    output_format="markdown",
    session_id="rate-limit-design"
)
```

**Key parameters:**

| Parameter | Description | Default |
|-----------|-------------|---------|
| `model` | Model name (e.g., `gpt-5.2`, `gemini-3-pro-preview`) | Required |
| `question` | The question or prompt | Required |
| `output_format` | Response format (plain text, markdown, JSON) | Required |
| `session_id` | Conversation identifier | Required |

**When to use consult_with:**
- Getting a quick second opinion
- Design discussions without code changes
- Model comparison for the same question
- When file access isn't needed

## Core Concepts

### 1. Context Management

Context management primarily applies to `consult_with` and the underlying API tools. The `work_with` tool uses CLI agents that have their own file access.

**For consult_with:**
```
# Context is not directly passed to consult_with
# Use it for questions where you provide context inline
consult_with(
    model="gpt-5.2-pro",
    question="Given this code: [paste code], what's wrong?",
    output_format="markdown",
    session_id="debug"
)
```

### 2. Session Management

Sessions enable multi-turn conversations with memory persistence.

```
session_id: "jwt-auth-refactor-2024-12-10"
```

**Best practices:**
- One session per logical thread of reasoning
- Use descriptive IDs: `debug-race-condition-2024-12-10`
- Reuse same `session_id` for follow-ups (conversation continues)
- Sessions work across tools AND models (unified session system)
- Default TTL: 6 months

**Cross-tool session continuity:**
```
# Start with work_with (agentic exploration)
work_with(
    agent="claude-sonnet-4-5",
    task="Analyze the auth module",
    session_id="auth-analysis"
)

# Continue with consult_with (quick opinion)
consult_with(
    model="gpt-5.2-pro",
    question="Based on our analysis, what's the best refactoring approach?",
    output_format="markdown",
    session_id="auth-analysis"  # Same session - has context from work_with
)

# Back to work_with with a different model
work_with(
    agent="gemini-3-pro-preview",
    task="Implement the refactoring we discussed",
    session_id="auth-analysis"  # Continues the conversation
)
```

### 3. Structured Output

For `consult_with` with JSON output:

```
consult_with(
    model="gpt-5.2",
    question="List the issues in this code",
    output_format="JSON with schema: {issues: string[], severity: 'low'|'medium'|'high'}",
    session_id="analysis"
)
```

### 4. Reasoning Effort

Control depth of model thinking (supported by `work_with`):

| Level | Use Case | Models |
|-------|----------|--------|
| `low` | Quick answers | All |
| `medium` | Balanced (default) | All |
| `high` | Deep analysis | All |
| `xhigh` | Maximum depth | gpt-5.2-pro, gpt-5.1-codex-max |

```
work_with(
    agent="gpt-5.2-pro",
    task="Debug this complex race condition",
    session_id="debug",
    reasoning_effort="high"  # For complex problems
)
```

## Utility Tools

### Project History Search

Search past conversations AND git commits:

```
search_project_history(
    query="JWT authentication decisions; refresh token strategy",
    max_results=20,
    store_types=["conversation", "commit"]
)
```

**Important:** Returns HISTORICAL data that may be outdated. Use to understand past decisions, not current code state.

### Session Management

```
list_sessions(limit=10, include_summary=true)
describe_session(session_id="auth-analysis")
```

### Token Counting

Estimate context size:

```
count_project_tokens(
    items=["/src", "/tests"],
    top_n=10  # Show top 10 largest files
)
```

### Deep Research (Async)

For exhaustive web research:

```
# Comprehensive research (10-60 min)
research_with_o3_deep_research(
    instructions="Research best practices for JWT rotation",
    output_format="Report with citations",
    session_id="jwt-research"
)

# Quick reconnaissance (2-10 min)
research_with_o4_mini_deep_research(
    instructions="What are competitors doing for auth?",
    output_format="Bullet points with links",
    session_id="competitive-research"
)
```

### Async Jobs

For operations >60s:

```
# Start background job
job = start_job(
    target_tool="research_with_o3_deep_research",
    args={"instructions": "...", "session_id": "..."},
    max_runtime_s=3600
)

# Poll until complete
result = poll_job(job_id=job["job_id"])
# status: pending | running | completed | failed | cancelled

# Cancel if needed
cancel_job(job_id=job["job_id"])
```

## Multi-Model Collaboration (GroupThink)

Orchestrate multiple models on complex problems:

```
group_think(
    session_id="design-auth-system",
    objective="Design zero-downtime auth service with JWT rotation",
    models=[
        "chat_with_gpt52_pro",         # Best reasoning
        "chat_with_gemini3_pro_preview", # Large context analysis
        "chat_with_claude45_opus"        # Design documentation
    ],
    output_format="Design doc with: Architecture, API endpoints, Migration plan",
    context=["/src/auth"],
    priority_context=["/docs/security-requirements.md"],
    discussion_turns=6,
    validation_rounds=2
)
```

**How it works:**
1. **Discussion phase**: Models take turns contributing to shared whiteboard
2. **Synthesis phase**: Large-context model creates final deliverable
3. **Validation phase**: Original models review and critique

**Key parameters:**

| Parameter | Purpose | Default |
|-----------|---------|---------|
| `session_id` | Panel identifier (reuse to continue) | Required |
| `objective` | Problem to solve | Required |
| `models` | List of internal model tool names | Required |
| `output_format` | Deliverable specification | Required |
| `discussion_turns` | Back-and-forth rounds | 6 |
| `validation_rounds` | Review iterations | 2 |
| `synthesis_model` | Model for final synthesis | gemini3_pro_preview |
| `direct_context` | Inject history directly (vs vector search) | true |

## Model Selection Strategies

### For Debugging

```
# Fast hypothesis generation
consult_with(
    model="gemini-3-flash-preview",
    question="What could cause this error: [error]",
    output_format="bullet list",
    session_id="debug-1"
)

# Deep investigation
work_with(
    agent="claude-sonnet-4-5",
    task="Investigate and fix the [hypothesis] issue",
    session_id="debug-1",
    reasoning_effort="high"
)
```

### For Code Review

```
# Get the AI to review your changes
work_with(
    agent="claude-sonnet-4-5",
    task="Review the recent changes in src/auth for security issues",
    session_id="code-review",
    role="codereviewer"
)

# Get a second opinion
consult_with(
    model="gpt-5.2-pro",
    question="Here's what Claude found: [summary]. Anything missed?",
    output_format="markdown",
    session_id="code-review"
)
```

### For Architecture Design

```
# Use GroupThink for complex design
group_think(
    session_id="api-design",
    objective="Design RESTful API for user management",
    models=["chat_with_gpt52_pro", "chat_with_gemini3_pro_preview"],
    output_format="OpenAPI spec with implementation notes"
)

# Or step-by-step with work_with
work_with(
    agent="gpt-5.2-pro",
    task="Design the API structure",
    session_id="api-design-manual",
    role="planner"
)
```

## Error Handling

### Rate Limits (429)
- Stagger launches by 100ms
- Use async jobs for high concurrency
- Fallback to cheaper models

### Context Overflow
- Run `count_project_tokens` first
- Switch to larger-context model (gpt-4.1, gemini-3-pro-preview)
- Let server handle vector store split for GroupThink

### Timeouts
- Offload to `start_job` / `poll_job`
- Use faster models for initial scan
- Break into smaller queries

## Configuration

### Environment Variables
```bash
OPENAI_API_KEY="sk-..."
GEMINI_API_KEY="..."
XAI_API_KEY="xai-..."
ANTHROPIC_API_KEY="sk-ant-..."
VERTEX_PROJECT="my-project"
VERTEX_LOCATION="us-central1"
```

### Key Settings (config.yaml)
```yaml
mcp:
  context_percentage: 0.85  # % of model context to use
  default_temperature: 0.2

session:
  ttl_seconds: 15552000  # 6 months

history:
  enabled: true
```

## Best Practices Summary

1. **Choose the right tool**: `work_with` for action, `consult_with` for advice
2. **Start Fast, Go Deep**: Use flash models for exploration, then targeted deep models
3. **Session Hygiene**: One session per logical thread of reasoning
4. **Cross-tool sessions**: Same session_id works across work_with and consult_with
5. **Smart Fallbacks**: Always have a faster/cheaper model as backup
6. **Reasoning Effort**: Use `high`/`xhigh` only for complex problems
7. **Reuse Sessions**: Save tokens by continuing conversations
8. **Check History First**: Search project history before making decisions
9. **Monitor Tokens**: Use `count_project_tokens` for large contexts
10. **Async for Long Tasks**: Use job system for >60s operations

## Resources

This skill includes quick-reference materials in `references/`:

- **model-selection-guide.md**: Detailed model comparison and selection criteria
- **common-patterns.md**: Copy-paste patterns for common workflows

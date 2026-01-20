# Model Selection Guide

Quick decision tree for choosing the right model with `work_with` and `consult_with`.

## Decision Tree

```
What do you need?
│
├─► Code changes or file exploration
│   └─► work_with (agentic CLI agents)
│       ├─► Claude Code → claude-sonnet-4-5 (best coding)
│       ├─► Gemini CLI → gemini-3-pro-preview (1M context)
│       └─► Codex CLI → gpt-5.2 (strong reasoning)
│
├─► Quick opinion/analysis (no file access)
│   └─► consult_with (API models)
│       ├─► Speed critical → gemini-3-flash-preview (1M, very fast)
│       ├─► Quality critical → gpt-5.2-pro (400k, best reasoning)
│       └─► Large context → gpt-4.1 (1M, reliable)
│
├─► Large context (>400k tokens)
│   ├─► Need speed? → gemini-3-flash-preview (1M)
│   ├─► Need quality? → gemini-3-pro-preview (1M)
│   ├─► Need reliability? → gpt-4.1 (1M, low hallucination)
│   └─► Massive (>1M)? → grok-4.1 (~2M)
│
├─► Web research needed
│   ├─► Deep, exhaustive? → research_with_o3_deep_research (10-60 min)
│   ├─► Quick scan? → research_with_o4_mini_deep_research (2-10 min)
│   └─► Live/Twitter? → consult_with grok-4.1 (Live Search)
│
└─► Multi-perspective needed
    └─► group_think with 3-4 diverse models
```

## Tool Selection: work_with vs consult_with

| Scenario | Tool | Model | Why |
|----------|------|-------|-----|
| Debug a bug | `work_with` | `claude-sonnet-4-5` | Needs to read code |
| Architecture opinion | `consult_with` | `gpt-5.2-pro` | Just needs to reason |
| Implement feature | `work_with` | `claude-sonnet-4-5` | Needs to write code |
| Code review feedback | `work_with` | `claude-sonnet-4-5` | Needs to read changes |
| Design discussion | `consult_with` | `gemini-3-pro-preview` | Discussion, no action |
| Quick error analysis | `consult_with` | `gemini-3-flash-preview` | Fast hypothesis |
| Refactor codebase | `work_with` | `claude-sonnet-4-5` | Needs autonomous action |

## Model Comparison Matrix

| Model | Context | Speed | Reasoning | Code | Writing | Cost |
|-------|---------|-------|-----------|------|---------|------|
| **gpt-5.2-pro** | 400k | Medium | ★★★★★ | ★★★★★ | ★★★★ | $$$$ |
| **gpt-5.2** | 272k | Medium | ★★★★ | ★★★★★ | ★★★★ | $$$ |
| **gpt-5.1-codex-max** | 272k | Medium | ★★★★★ | ★★★★★ | ★★★★ | $$$$ |
| **gpt-4.1** | 1M | Fast | ★★★★ | ★★★★ | ★★★★ | $$$ |
| **gemini-3-pro-preview** | 1M | Medium | ★★★★ | ★★★★★ | ★★★★ | $$$ |
| **gemini-3-flash-preview** | 1M | Very Fast | ★★★ | ★★★ | ★★★ | $ |
| **claude-opus-4-5** | 200k | Slow | ★★★★★ | ★★★★ | ★★★★★ | $$$$$ |
| **claude-sonnet-4-5** | 1M | Fast | ★★★★ | ★★★★★ | ★★★★★ | $$$ |
| **grok-4.1** | ~2M | Medium | ★★★★ | ★★★ | ★★★★ | $$$ |

## Task-Specific Recommendations

### Code Analysis & Review
```
# Use work_with for thorough code review
work_with(
    agent="claude-sonnet-4-5",
    task="Review src/auth for security issues",
    session_id="code-review",
    role="codereviewer"
)

# Use consult_with for quick opinion on pasted code
consult_with(
    model="gpt-5.2-pro",
    question="Is this implementation secure? [code]",
    output_format="markdown",
    session_id="quick-review"
)
```

### Code Generation
```
# Use work_with for implementation
work_with(
    agent="claude-sonnet-4-5",
    task="Implement JWT authentication for the API",
    session_id="jwt-impl"
)
```

### Documentation
```
# Use work_with to generate docs from code
work_with(
    agent="claude-sonnet-4-5",
    task="Generate API documentation for src/api",
    session_id="docs"
)

# Use consult_with for writing style advice
consult_with(
    model="claude-opus-4-5",
    question="How should I document this API pattern?",
    output_format="markdown",
    session_id="doc-advice"
)
```

### Debugging
```
# Phase 1: Quick hypothesis with consult_with
consult_with(
    model="gemini-3-flash-preview",
    question="What could cause this error: [error]",
    output_format="bullet list",
    session_id="debug"
)

# Phase 2: Deep investigation with work_with
work_with(
    agent="claude-sonnet-4-5",
    task="Investigate the race condition in auth module",
    session_id="debug",
    reasoning_effort="high"
)
```

### Research
1. `research_with_o3_deep_research` - Comprehensive, cited (10-60 min)
2. `research_with_o4_mini_deep_research` - Quick reconnaissance (2-10 min)
3. `consult_with` + `grok-4.1` - Live/social media context

### Architecture Design
```
# Option 1: GroupThink for multi-perspective design
group_think(
    session_id="api-design",
    objective="Design RESTful API for user management",
    models=["chat_with_gpt52_pro", "chat_with_gemini3_pro_preview"],
    output_format="OpenAPI spec"
)

# Option 2: work_with with planner role
work_with(
    agent="gpt-5.2-pro",
    task="Design the authentication architecture",
    session_id="arch-design",
    role="planner"
)
```

## Capability Quick Reference

| Capability | Models |
|------------|--------|
| **CLI Agents (work_with)** | claude-*, gemini-3-*, gpt-5.2, gpt-4.1 |
| **Web Search** | gpt-5.2-pro, gpt-4.1, grok-4.1, research_* |
| **Reasoning Effort** | All (via work_with) |
| **Extended Thinking** | claude-opus-4-5, claude-sonnet-4-5 |
| **Live Search (X)** | grok-4.1 |
| **Multimodal (Vision)** | gemini-*, claude-* |

## Cost Optimization Strategy

```
Start cheap, escalate as needed:

1. consult_with + gemini-3-flash-preview ($)    → Quick scan, hypothesis
2. consult_with + gpt-4.1 ($$$)                 → If more depth needed
3. work_with + claude-sonnet-4-5 ($$$)          → When action required
4. consult_with + gpt-5.2-pro ($$$$)            → Maximum reasoning quality
```

## GroupThink Model Combinations

Note: GroupThink still uses internal `chat_with_*` tool names.

### Balanced Panel (General Purpose)
```
models=[
    "chat_with_gpt52_pro",            # Reasoning
    "chat_with_gemini3_pro_preview",  # Code analysis
    "chat_with_claude45_opus"         # Writing
]
```

### Code-Heavy Panel
```
models=[
    "chat_with_gpt52_pro",            # Complex logic
    "chat_with_gemini3_pro_preview",  # Patterns
    "chat_with_gpt41"                 # Review
]
```

### Research Panel
```
models=[
    "chat_with_gpt52_pro",            # Synthesis
    "chat_with_grok41",               # Live context
    "chat_with_claude45_opus"         # Documentation
]
```

## Reasoning Effort Guide

When using `work_with`, adjust reasoning_effort based on task complexity:

| Level | When to Use | Example Tasks |
|-------|-------------|---------------|
| `low` | Simple, clear tasks | "Add a log statement", "Rename variable" |
| `medium` | Standard tasks (default) | "Implement feature X", "Fix this bug" |
| `high` | Complex problems | "Debug race condition", "Optimize algorithm" |
| `xhigh` | Hardest problems | "Design distributed system", "Security audit" |

```
# Simple task - low reasoning
work_with(agent="claude-sonnet-4-5", task="Add logging", reasoning_effort="low", ...)

# Complex debugging - high reasoning
work_with(agent="gpt-5.2-pro", task="Debug memory leak", reasoning_effort="high", ...)
```

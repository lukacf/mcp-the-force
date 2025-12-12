# Model Selection Guide

Quick decision tree for choosing the right model.

## Decision Tree

```
What do you need?
│
├─► Speed is critical
│   └─► chat_with_gemini25_flash (1M, very fast)
│
├─► Quality is critical
│   ├─► Extended reasoning needed? → chat_with_gpt52_pro (400k, best reasoning)
│   ├─► 24+ hour task? → chat_with_gpt51_codex_max (400k, xhigh, auto-compaction)
│   └─► Premium writing? → chat_with_claude45_opus (200k, extended thinking)
│
├─► Large context (>400k tokens)
│   ├─► Need speed? → chat_with_gemini25_flash (1M)
│   ├─► Need quality? → chat_with_gemini3_pro_preview (1M)
│   ├─► Need reliability? → chat_with_gpt41 (1M, low hallucination)
│   └─► Massive (>1M)? → chat_with_grok41 (~2M)
│
├─► Web research needed
│   ├─► Deep, exhaustive? → research_with_o3_deep_research (10-60 min)
│   ├─► Quick scan? → research_with_o4_mini_deep_research (2-10 min)
│   └─► Live/Twitter? → chat_with_grok41 (Live Search)
│
└─► Multi-perspective needed
    └─► group_think with 3-4 diverse models
```

## Model Comparison Matrix

| Model | Context | Speed | Reasoning | Code | Writing | Cost |
|-------|---------|-------|-----------|------|---------|------|
| **gpt52_pro** | 400k | Medium | ★★★★★ | ★★★★★ | ★★★★ | $$$$ |
| **gpt51_codex_max** | 400k | Slow | ★★★★★+ | ★★★★★ | ★★★★ | $$$$$ |
| **gpt41** | 1M | Fast | ★★★★ | ★★★★ | ★★★★ | $$$ |
| **gemini3_pro** | 1M | Medium | ★★★★ | ★★★★★ | ★★★★ | $$$ |
| **gemini25_flash** | 1M | Very Fast | ★★★ | ★★★ | ★★★ | $ |
| **claude45_opus** | 200k | Slow | ★★★★★ | ★★★★ | ★★★★★ | $$$$$ |
| **claude45_sonnet** | 1M | Fast | ★★★★ | ★★★★ | ★★★★★ | $$$ |
| **claude3_opus** | 200k | Slow | ★★★★ | ★★★ | ★★★★★ | $$$$ |
| **grok41** | ~2M | Medium | ★★★★ | ★★★ | ★★★★ | $$$ |

## Task-Specific Recommendations

### Code Analysis & Review
1. `chat_with_gpt52_pro` - Best reasoning for complex issues
2. `chat_with_gemini3_pro_preview` - Large codebase analysis
3. `chat_with_gpt41` - Reliable, low hallucination

### Code Generation
1. `chat_with_gpt52_pro` - Complex logic, algorithms
2. `chat_with_gemini3_pro_preview` - Boilerplate, scaffolding
3. `chat_with_gpt41` - Quick reliable generation

### Documentation
1. `chat_with_claude45_opus` - Premium technical writing
2. `chat_with_claude45_sonnet` - Fast, quality docs
3. `chat_with_gemini3_pro_preview` - Large context summaries

### Debugging
1. `chat_with_gemini25_flash` - Quick hypothesis (Phase 1)
2. `chat_with_gpt52_pro` - Deep trace analysis (Phase 2)
3. `chat_with_gpt41` - Cross-reference validation

### Research
1. `research_with_o3_deep_research` - Comprehensive, cited
2. `research_with_o4_mini_deep_research` - Quick reconnaissance
3. `chat_with_grok41` - Live/social media context

### Architecture Design
1. `group_think` with multiple models
2. `chat_with_gpt52_pro` - Reasoning about trade-offs
3. `chat_with_claude45_opus` - Design documentation

## Capability Quick Reference

| Capability | Models |
|------------|--------|
| **Web Search** | gpt52_pro, gpt41, grok41, research_* |
| **Structured Output** | All except research models |
| **Reasoning Effort** | gpt52_pro, gpt51_codex_max, research_* |
| **Temperature** | gpt41, gemini*, grok*, claude* |
| **Extended Thinking** | claude45_opus, claude45_sonnet |
| **Live Search (X)** | grok41 |
| **Multimodal (Vision)** | gemini*, claude* |

## Cost Optimization Strategy

```
Start cheap, escalate as needed:

1. gemini25_flash ($)     → Quick scan, hypothesis
2. gpt41 ($$$)            → If more depth needed
3. gpt52_pro ($$$$)        → If reasoning quality matters
4. gpt51_codex_max ($$$$$) → Only for long-horizon tasks
```

## GroupThink Model Combinations

### Balanced Panel (General Purpose)
```
models=[
    "chat_with_gpt52_pro",            # Reasoning
    "chat_with_gemini3_pro_preview", # Code analysis
    "chat_with_claude45_opus"        # Writing
]
```

### Code-Heavy Panel
```
models=[
    "chat_with_gpt52_pro",            # Complex logic
    "chat_with_gemini3_pro_preview", # Patterns
    "chat_with_gpt41"                # Review
]
```

### Research Panel
```
models=[
    "chat_with_gpt52_pro",            # Synthesis
    "chat_with_grok41",              # Live context
    "chat_with_claude45_opus"        # Documentation
]
```

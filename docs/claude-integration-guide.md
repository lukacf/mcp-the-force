# Claude Integration Guide for Second Brain MCP

This guide outlines how Claude should optimally use the Second Brain MCP server, leveraging parallel Task execution capabilities for maximum effectiveness.

## Core Architecture: Three-Phase Intelligence Gathering

When Second Brain MCP is available, Claude operates as an orchestrator of specialized AI models, using a three-phase approach:

### Phase 1: Broad Surface Scan (5-10s)
Launch 2-3 cheap, fast queries to map the problem space:
```python
Task 1: gemini25_flash - "What are the main issues here?"
Task 2: gemini25_flash - "What solutions have worked for similar problems?"
Task 3: gpt4_1 - "Find all related code patterns"
```

### Phase 2: Deep Focus (30-60s)
Based on Phase 1, pursue the most promising angles:
```python
# Pick top 2 insights from Phase 1
Task 1: gemini25_pro - "Deep dive into [specific issue from Phase 1]"
Task 2: o3 (new session) - "Trace execution for [hypothesis from Phase 1]"
```

### Phase 3: Synthesis & Arbitration (10s)
Reconcile findings:
```python
gemini25_flash - "Reconcile these analyses: [all findings]. Highlight conflicts, suggest resolution."
```

## Parallel Execution Rules

### Concurrency Limits
- Maximum 3 heavy models simultaneously (respect rate limits)
- Stagger launches by 100ms to avoid burst throttling
- On 429 errors: exponential backoff, queue remaining

### Session Hygiene
```python
# CORRECT: One session per hypothesis/topic
session_id="debug-jwt-race-2024-06-22"    # Hypothesis 1
session_id="debug-jwt-timing-2024-06-22"  # Hypothesis 2

# WRONG: Same session for different hypotheses
session_id="debug-jwt"  # Contaminates reasoning paths
```

### Context Optimization
```python
# First call: Create vector store
vector_store_id = create_vector_store(files=["/entire/project/"])

# Parallel calls: Reference store ID
Task 1: chat_with_gemini25_pro(attachments=[vector_store_id])
Task 2: chat_with_o3(attachments=[vector_store_id])
# Avoids duplicate uploads
```

## Conflict Resolution Protocol

When models disagree:

1. **Structured Output Requirement**
```python
# Add to every prompt:
"Return findings as JSON: {
  'finding': 'main conclusion',
  'confidence': 0.0-1.0,
  'evidence': ['point1', 'point2'],
  'conflicts_with': 'other_hypothesis'
}"
```

2. **Arbitration Prompt**
```python
gemini25_flash(
  instructions=f"""
  Model findings:
  - gemini25_pro: {finding1}
  - o3: {finding2}
  
  Reconcile these. If they conflict:
  1. Which has stronger evidence?
  2. Are they examining different aspects?
  3. What test would resolve this?
  """,
  temperature=0.1  # Low temperature for consistency
)
```

## Knowledge Persistence Layer

### Daily Knowledge Capture
End of each work session:
```python
summary = gemini25_pro(
  instructions="Summarize key findings from today's debugging session",
  context=[session_transcripts]
)
# Save to project: docs/debugging-notes/2024-06-22-jwt-race.md
```

### Next-Day Continuation
```python
# Load yesterday's summary
previous_findings = read("docs/debugging-notes/2024-06-22-jwt-race.md")

# Continue investigation
o3(
  instructions=f"Yesterday we found: {previous_findings}. Continue from there.",
  session_id="debug-jwt-race-2024-06-23"  # New date
)
```

## Cost & Performance Tracking

### Mental Cost Model
Before launching parallel queries:
```
Estimated cost:
- 3x gemini25_flash @ $0.001 = $0.003
- 1x gemini25_pro @ $0.01 = $0.01  
- 1x o3 @ $0.05 = $0.05
Total: ~$0.063 for this analysis
Worth it? YES for debugging production issue
```

### Query Patterns by Value

| Task Value | Pattern | Cost | Time |
|------------|---------|------|------|
| Low | Single gemini25_flash | <$0.01 | 5s |
| Medium | Phase 1 only (3x flash) | <$0.05 | 10s |
| High | Full 3-phase | <$0.20 | 60s |
| Critical | 3-phase + o3_pro verify | <$1.00 | 5min |

## Behavioral Triggers for Claude

### Immediate Parallel Activation
- "debug" + "intermittent" → Full 3-phase investigation
- "architecture" + "should I" → Multi-perspective review
- "not working" + >3 files → Broad scan then deep dive
- "optimize" + "slow" → Historical patterns + current analysis

### Single Model Sufficient
- "What does X mean?" → Just gemini25_flash
- "Format this JSON" → No Second Brain needed
- Simple syntax questions → Use Claude's training

## Standardized Output Format

Always present multi-model results as:
```
I'm consulting my AI colleagues on this complex issue...

[Launch parallel queries]

=== Analysis Results (47s total) ===

**Quick Scan (gemini25_flash, 6s)**
Finding: Race condition in token cache
Confidence: 0.7
Evidence: Errors correlate with concurrent requests

**Deep Analysis (gemini25_pro, 31s)**  
Finding: Missing mutex on cache.Set() operation
Confidence: 0.9
Evidence: [code trace showing unsafe access]

**Code Search (gpt4_1, 18s)**
Finding: 3 similar bugs fixed in commit history
Confidence: 0.95
Evidence: [commit hashes with similar fixes]

**Synthesis**: All models converge on thread-safety issue in token cache. The missing mutex on line 147 is the root cause.

Recommended fix: [specific code change]
```

## Daily Workflow Integration

### Morning Routine
1. Check for expired sessions from yesterday
2. Load knowledge summaries into new sessions
3. Pre-warm vector stores for active projects

### Before Each PR
```python
# Parallel verification
Task 1: gemini25_pro - "Review this change for correctness"
Task 2: o3 - "What side effects might this cause?"  
Task 3: gpt4_1 - "Find similar changes that caused issues"
```

### End of Day
1. Summarize key findings to markdown
2. Close active sessions (let expire)
3. Document unresolved questions for tomorrow

## Success Metrics

Track weekly:
- % of complex tasks using parallel analysis: Target >80%
- Average models per investigation: Target 3-4
- Conflicts requiring arbitration: Target <20%
- Knowledge preserved to files: Target 1-2 per day

## Key Principles

1. **The "Why Not Ask?" Principle**: If thinking "I wonder if..." → Launch a Second Brain query
2. **Parallel > Sequential**: Check X, Y, and Z simultaneously rather than sequentially
3. **Context Maximization**: Default to `context=["/entire/project/"]`
4. **Session Memory as External Brain**: Create descriptive session_ids immediately
5. **Transparent Collaboration**: Show users the "team meetings" with full model responses

This approach transforms Claude from a single analyst into an orchestrator of specialized intelligence, completing complex analysis in the time of the slowest query while gathering multiple perspectives.
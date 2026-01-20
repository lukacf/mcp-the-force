# The Force MCP – Usage Guide for LLM Agents

## Core Concepts
- **Two primary tools:** Use `work_with` for agentic tasks (CLI agents with file access) and `consult_with` for quick opinions (API models without file access).
- **Unified sessions:** Session IDs work across both tools. Start with `work_with`, continue with `consult_with`, and switch back seamlessly.
- **Model names:** Use model names like `claude-sonnet-4-5`, `gpt-5.2-pro`, `gemini-3-pro-preview` with both tools.

## Primary Tools

### work_with (Agentic Tasks)
Spawns CLI agents (Claude Code, Gemini CLI, Codex CLI) that can read files, run commands, and take action.

```
work_with(
    agent="claude-sonnet-4-5",
    task="Review auth flow and fix any security issues",
    session_id="auth-audit",
    role="default",           # default, planner, codereviewer
    reasoning_effort="medium" # low, medium, high, xhigh
)
```

**Parameters:**
- `agent`: Model name (e.g., `claude-sonnet-4-5`, `gpt-5.2`, `gemini-3-pro-preview`)
- `task`: The task for the agent
- `session_id`: Conversation identifier (reuse to continue)
- `role`: System prompt role (default, planner, codereviewer)
- `reasoning_effort`: Reasoning depth (low/medium/high/xhigh)

### consult_with (Quick Opinions)
Routes to API models for fast analysis without file access.

```
consult_with(
    model="gpt-5.2-pro",
    question="What are the security implications of this approach?",
    output_format="markdown",
    session_id="auth-audit"
)
```

**Parameters:**
- `model`: Model name (same as work_with)
- `question`: The question or prompt
- `output_format`: Response format (plain text, markdown, JSON)
- `session_id`: Conversation identifier

## Utility Tools
- `search_project_history`: Semantic search over past chats and git commits.
- `list_sessions` / `describe_session`: List or summarize saved sessions.
- `count_project_tokens`: Estimate token sizes before sending large contexts.

## Asynchronous Jobs (longer than 60s)
- `start_job` → enqueue any tool. Returns `job_id`.
- `poll_job` → check `pending|running|completed|failed|cancelled` and get the result.
- `cancel_job` → best-effort cancel a pending/running job.
- Jobs persist in `.mcp-the-force/jobs.sqlite3`; a background worker runs during server lifespan.
- Pattern: `start_job` → poll with `poll_job` until done. Use for expensive vector builds, deep research, large token counts.

## GroupThink (multi-model collaboration)
- Tool: `group_think`
  Params: `models` (list of internal `chat_with_*` tool names), `objective`, `output_format`, `session_id`, optional `discussion_turns`, `max_steps`, `validation_rounds`.
- Behavior: orchestrates multiple models on a shared "whiteboard", then synthesizes a final deliverable.
- Tips: give a clear objective and expected output format; set `discussion_turns` modestly (6–10) to avoid timeouts; reuse `session_id` to continue a prior panel.
- Long topics: if you risk >60s, launch via `start_job` and poll results.

## Best Practices
- **Choose the right tool:** `work_with` for action, `consult_with` for advice.
- Keep `session_id` consistent for multi-turn threads; it works across both tools.
- Use `reasoning_effort="high"` for complex problems with `work_with`.
- If a model is unavailable, switch to another.

## Troubleshooting
- **401/invalid key:** check `.mcp-the-force/secrets.yaml` or env vars (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY`).
- **Tool timeout:** offload to `start_job`/`poll_job`.
- **Context too large:** run `count_project_tokens`, trim, or use `work_with` which has native file access.

## Examples

### Agentic code review:
```
work_with(
    agent="claude-sonnet-4-5",
    task="Review auth flow and identify security issues",
    session_id="auth-audit",
    role="codereviewer"
)
```

### Quick opinion:
```
consult_with(
    model="gpt-5.2-pro",
    question="Is JWT or session tokens better for our mobile API?",
    output_format="markdown",
    session_id="auth-design"
)
```

### Cross-tool session continuity:
```
# Step 1: Agentic investigation
work_with(agent="claude-sonnet-4-5", task="Find security issues in auth", session_id="audit")

# Step 2: Get opinion on findings
consult_with(model="gpt-5.2-pro", question="How should we prioritize these issues?", output_format="markdown", session_id="audit")

# Step 3: Implement the fix
work_with(agent="claude-sonnet-4-5", task="Fix the highest priority issue", session_id="audit")
```

### Long task async:
```
start_job(target_tool="count_project_tokens", args={"items": ["/repo"], "top_n": 5})
# then poll_job(job_id="<returned_id>") until completed
```

## Notes for Agents
- Do not hardcode repo-relative paths; always send absolute paths when using context parameters.
- Avoid unnecessary tool calls when a direct answer suffices.
- You can run multiple async jobs in parallel; results persist across restarts.

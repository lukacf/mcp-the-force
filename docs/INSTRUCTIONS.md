# The Force MCP – Usage Guide for LLM Agents

## Core Concepts
- **One interface, many models:** Use `chat_with_*` tools to access OpenAI (GPT‑5.1 Codex, o3), Google Gemini, Anthropic Claude, xAI Grok, etc.
- **Context management:** Pass absolute paths in `context`; small files are inlined, larger ones go to the vector store. Use `priority_context` to force-include must-read files.
- **Sessions:** Set `session_id` to retain history per model/tool. Stable inline lists prevent prompt drift.
- **JSON output:** Where supported, pass `structured_output_schema` for strict JSON replies.

## Everyday Tools
- `chat_with_<model>`: primary chat/generation. Params: `instructions`, `context`, `priority_context`, `session_id`, `temperature`, `structured_output_schema` (where supported).
- `search_project_history`: semantic search over past chats and git commits.
- `list_sessions` / `describe_session`: list or summarize saved sessions.
- `count_project_tokens`: estimate token sizes before sending large contexts.

## Asynchronous Jobs (longer than 60s)
- `start_job` → enqueue any tool. Returns `job_id`.
- `poll_job` → check `pending|running|completed|failed|cancelled` and get the result.
- `cancel_job` → best-effort cancel a pending/running job.
- Jobs persist in `.mcp-the-force/jobs.sqlite3`; a background worker runs during server lifespan.
- Pattern: `start_job` → poll with `poll_job` until done. Use for expensive vector builds, deep research, large token counts.

## GroupThink (multi-model collaboration)
- Tool: `group_think`  
  Params: `models` (list, e.g., `["chat_with_gpt51_codex","chat_with_gemini3_pro_preview","chat_with_claude45_sonnet","chat_with_grok41"]`), `objective`, `output_format`, `session_id`, optional `discussion_turns`, `max_steps`, `validation_rounds`.
- Behavior: orchestrates multiple models on a shared “whiteboard”, then synthesizes a final deliverable.
- Tips: give a clear objective and expected output format; set `discussion_turns` modestly (6–10) to avoid timeouts; reuse `session_id` to continue a prior panel.
- Long topics: if you risk >60s, launch via `start_job` and poll results.

## Best Practices
- Always use **absolute paths** in `context` and `priority_context`.
- Keep `session_id` consistent for multi-turn threads; you can reuse across models if desired.
- For must-include files, prefer `priority_context`; use broader sets in `context`.
- If a model is unavailable, switch to another (e.g., `chat_with_gpt41` for fast fallback).
- Gemini tool calls require thought signatures; the current build handles this automatically.

## Troubleshooting
- **401/invalid key:** check `.mcp-the-force/secrets.yaml` or env vars (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY`).
- **Tool timeout:** offload to `start_job`/`poll_job`.
- **Context too large:** run `count_project_tokens`, trim, rely on vector store.
- **Gemini thoughtSignature errors:** ensure the server is on the latest build; restart after upgrades.

## Examples
- Analyze auth flow:  
  `chat_with_gpt51_codex {"instructions": "Review auth flow", "context": ["/repo/app"], "priority_context": ["/repo/app/auth.py"], "session_id": "auth-audit"}`
- Long task async:  
  `start_job {"target_tool": "count_project_tokens", "args": {"items": ["/repo"], "top_n": 5}}`  
  then `poll_job {"job_id": "<returned_id>"}` until `completed`.

## Notes for Agents
- Do not hardcode repo-relative paths; always send absolute paths.
- Avoid unnecessary tool calls when a direct answer suffices.
- You can run multiple async jobs in parallel; results persist across restarts.

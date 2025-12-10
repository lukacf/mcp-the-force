# Changelog

## 1.2.1
### New Features
- **GPT-5.1-Codex-Max**: Added OpenAI's new long-horizon agentic coding model with `xhigh` reasoning effort, 400k context, 90-minute timeout, and automatic compaction for 24+ hour tasks. 77.9% on SWE-bench Verified.
- **Group Think Reliability**: Added retry with model fallback for synthesis and validation phases to prevent wasting multi-turn discussions on transient API failures.
- **Direct Context Injection**: Added `direct_context` parameter to group_think for reliable multi-turn collaboration without vector store dependency.
- **Force Guide Tools**: Added `list_guides` and `read_guide` tools with robust fallbacks for accessing documentation.
- **Async Job Improvements**: Jobs now respect `max_runtime_s` instead of tool timeout; increased default tool timeouts to 30 min for heavyweight models.

### Bug Fixes
- **Security**: Removed API key values from debug log output, now logs only boolean presence indicators.
- **Reasoning Effort Defaults**: Fixed issue where models with non-medium defaults (xhigh, high) weren't getting their intended reasoning effort. User-explicit values are always respected.
- **Google Adapter**: Fixed Gemini API key priority over Vertex AI; explicitly override Vertex AI env vars when using Gemini API key.
- **Group Think**: Fixed continuation bugs, empty response validation, conversation_input sanitization, and session reactivation.
- **LiteLLM**: Fixed content type bug and call_id sync between function_call and function_call_output pairs; handle overlapping function_calls with same call_id.
- **Instructions Tool**: Robust fallback to package docs or inline guide.

### Test & CI
- Added Claude Code GitHub Workflow for automated testing.
- Added 13 new regression tests for GPT-5.1-Codex-Max capabilities and reasoning_effort defaults.
- Fixed integration tests for timeout and flaky multiprocess issues.

## 1.2.0
- Added OpenAI `gpt-5-pro` model (400k context, high reasoning/tooling) with full blueprint/capability support and docs.
- Replaced Anthropic Claude Opus 4.1 with Opus 4.5 (`claude-opus-4-5-20251101`), updating adapters, blueprints, docs, and tests.
- GroupThink: now returns cached deliverable if available and can resume when a session is marked complete without a stored output.
- Instructions tool: reads `docs/INSTRUCTIONS.md` with robust path fallback; added GroupThink guidance.

## 1.1.0
- Replaced legacy models with latest releases: OpenAI `gpt-5.1-codex` (400k), Google `gemini-3-pro-preview` (1M input), and xAI `grok-4.1` (~2M).
- Added Claude Sonnet 4.5 (1M context, beta header `context-1m-2025-08-07`) with updated capabilities, blueprints, and docs.
- Updated tool registry, prompts, documentation, and tests to the new model IDs and capabilities; clarified smoke E2E to target broadly available models.
- Dockerized E2E runner now ships a static Docker CLI to fix "docker not found" in compose-based tests.
- Added unit coverage for Sonnet 4.5 headers and adjusted anthropic blueprint expectations.
- Introduced asynchronous job queue with `start_job`, `poll_job`, and `cancel_job` tools backed by `jobs.sqlite3`, plus background worker lifecycle integration.

## 1.0.9
- Hardened vector-store deduplication against multiprocess races with per-hash token files plus token cleanup on finalize/rollback.
- Added optional `MCP_SERIALIZE_DEDUP=1` global mutex for noisy CI runners.
- Multiprocess atomic tests now use the safer `spawn` start method for cross-platform stability.

## 1.0.8
Added 1M context window support for Claude 4 Sonnet (claude-sonnet-4-20250514)
Fixed GPT-5 context window documentation to reflect 272k input limit (400k total including reasoning/output)
Added anthropic-beta header support for 1M context activation (context-1m-2025-08-07)
Enhanced tool parameter descriptions with discovery hints and improved formatting
Implemented smart beta header combination for multiple Anthropic features
Added comprehensive test coverage for 1M context functionality and header logic

## 1.0.7
Fixed XML escaping in context builder that was corrupting code syntax (e.g. "->" became "-&gt;")
Made file type filtering vector store-specific instead of global
Added supported_extensions property to all vector stores (OpenAI has restrictions, HNSW/InMemory accept all)
Fixed executor to use HNSW for non-OpenAI adapters when default is OpenAI to avoid unnecessary restrictions
Enhanced priority_context to allow explicit files to bypass .gitignore (directories still respect it)
Added diagnostic logging when vector stores drop files due to extension restrictions
Enhanced context parameter descriptions to show preferred array format over JSON strings
Added critical warnings to session_id parameter about conversation continuity
Added comprehensive unit tests for file filtering and XML escaping fixes

## 1.0.6
Added dynamic capability injection to model descriptions showing context window, tools, and features
Implemented model filtering to supported list of 17 AI models (excluding experimental/unavailable ones)
Enhanced model descriptions with summary, speed, tool use guidance, and recommended use cases
Updated documentation to highlight GPT-5 and Gemini 2.5 Pro as primary models for most tasks
Fixed unit tests to handle filtered models and updated test expectations
Added comprehensive capability formatter with human-readable output (e.g., "1M tokens" → "1M")
Fixed multiprocess cache race condition in tests for better CI stability
Fixed Ollama discovery tests for environments without psutil

## 1.0.5
Added GPT-5 model family support (gpt-5, gpt-5-mini, gpt-5-nano) with 400k context windows
Fixed history system to restore proper conversation summarization flow 
Added model-specific developer prompts with parallelized tool call instructions
Fixed Force conversations not showing in project history search
Added Ollama adapter with LiteLLM integration and model discovery  
Fixed deep research models to use web_search_preview tool correctly
Removed vestigial blueprint registration file to prevent conflicts

## 1.0.4
Fixed critical context loss bug with files over 500KB causing API retry failures
Added configurable file size limits (50MB per file, 200MB total)
Implemented deferred cache updates to prevent context loss on failed API calls

## 1.0.3
Upgraded Claude Opus to version 4.1
Added vector store deduplication system with two-level caching for cost reduction
Fixed hash collision bugs and cross-platform hashing inconsistencies
Enhanced vector store API optimization with parallel file uploads

## 1.0.2
Added TokenBudgetOptimizer for intelligent context management
Fixed critical context window overflow issues
Fixed history storage configuration bug (memory.sync → history.sync)

## 1.0.1
Added FusionTree algorithm for file tree representation (60-90% token savings)
Fixed deep research models to use web_search_preview tool

## 1.0.0
Initial public release with multi-provider AI model support
Added intelligent context management with vector store integration
Implemented multi-turn conversation support via UnifiedSessionCache
Added project history search across conversations and git commits

# GitHub Issues to Create

## 1. Improve System Prompts Throughout the Codebase
**Priority: High**

### Description
System prompts need improvement, especially for the summarization functionality. Currently the summarization prompt is basic and could be more sophisticated.

### Tasks
- Review and improve the memory summarization prompt in `conversation.py`
- Add better context about what makes a good searchable summary
- Consider adding examples of good vs bad summaries
- Review prompts for all AI model interactions
- Ensure prompts guide models to preserve key information for searchability

### Files to Update
- `/mcp_second_brain/memory/conversation.py` (summarization prompt)
- Any other files with AI prompts

---

## 2. Expose Memory Search Functions via MCP to Main Agent
**Priority: High**

### Description
Currently, search functions (`search_project_memory` and `search_session_attachments`) are only available to sub-agents (o3, Gemini, etc). The main Claude agent cannot directly search memory, which limits its effectiveness.

### Tasks
- Add `search_project_memory` as an MCP tool that Claude can call directly
- Add `search_session_attachments` as an MCP tool that Claude can call directly
- Ensure proper parameter validation and error handling
- Update documentation to explain when to use these tools

### Benefits
- Claude can directly search for past decisions, conversations, and context
- Reduces need to always go through sub-agents for memory access
- Improves overall system responsiveness

---

## 3. Rename "context" and "attachments" Parameters for Clarity
**Priority: Medium**

### Description
The parameter names "context" and "attachments" are ambiguous and cause confusion. LLMs often try to pass actual file content instead of file paths, leading to token waste and errors.

### Proposed Renames
- `context` → `context_file_paths` or `local_file_paths`
- `attachments` → `attachment_file_paths` or `vector_store_file_paths`

### Tasks
- Update all tool definitions to use clearer parameter names
- Update all documentation and docstrings
- Add explicit validation that rejects file content (only accepts paths)
- Add helpful error messages when content is passed instead of paths
- Update tests to use new parameter names

### Files to Update
- `/mcp_second_brain/tools/definitions.py`
- `/mcp_second_brain/tools/descriptors.py`
- All adapter files that handle these parameters
- All tests that use these parameters

---

## Additional Issues Discovered During Debugging

## 4. Fix High-Cost Vector Store Creation
**Priority: Critical**

### Description
As O3 pointed out, the system creates new OpenAI vector stores for every execution with attachments, which is expensive and will hit account limits.

### Tasks
- Implement vector store reuse/caching strategy
- Add vector store lifecycle management
- Monitor vector store costs
- Add limits to prevent runaway costs

---

## 5. Fix Race Conditions with ContextVars
**Priority: High**

### Description
Global `current_attachment_stores` can bleed between parallel calls, causing race conditions.

### Tasks
- Review all uses of ContextVars
- Ensure proper isolation between concurrent requests
- Add tests for concurrent execution
- Consider alternative approaches if ContextVars prove problematic

### Status
Resolved by passing attachment vector store IDs explicitly and ensuring
each execution uses its own list.

---

## 6. Refactor Monolithic OpenAIAdapter
**Priority: Medium**

### Description
The 900+ line OpenAIAdapter is difficult to test and maintain. It mixes HTTP, retry logic, streaming, and tool execution.

### Tasks
- Split into smaller, focused components
- Separate concerns (HTTP, streaming, tool execution, etc.)
- Add proper unit tests for each component
- Fix serial tool execution bottleneck (should be parallel)

---

## 7. Implement File Scanner Caching
**Priority: Medium**

### Description
File scanner has no caching and can follow symlink loops infinitely.

### Tasks
- Add caching layer for file scanning
- Implement symlink loop detection
- Add performance metrics
- Optimize for large codebases
This file provides guidance to you when working with code in this repository.

<critical_instructions>
**MANDATORY REQUIREMENTS - These override all other instructions:**

1. **Second Brain (MCP tools) Consultation is REQUIRED at These Checkpoints**:
   - Before ANY architectural decision or design pattern choice
   - When stuck on any problem or face unclarity
   - After completing each feature implementation
   - Before EVERY commit and pull request
   - After context window compression/reset

2. **Collaborative Approach - NOT Tool Usage**:
   - These are your AI colleagues, not tools. Consult them like you would senior developers. 
   - Use session_id for o3/o3_pro/gpt4_1 to maintain conversation continuity
   - Have real discussions - challenge their suggestions, ask follow-ups. Multi-turn is mandatory for o3/gpt4.1.

3. **Maintain Intellectual Independence**:
   - Ask "What's actually wrong?" not "How can I improve this?"
   - Reject over-engineered solutions to simple problems unless user has specifically given a direction
   - If assistants suggest massive changes for minor issues, push back
   - Synthesis ≠ consensus. Different perspectives are valuable.

4. **Know Your Colleagues**:
   - **o3/o3_pro**: Analytical reasoning, multi-turn conversations (use session_id)
   - **gemini25_pro**: Massive context windows (~1M tokens), smart, single-shot only
   - **gemini25_flash**: Massive context windows (~1M tokens), fast, single-shot only
   - **gpt4_1**: Massive context windows (~1M tokens), Web search for current info (use session_id)
   - All have knowledge cutoffs - o3 doesn't even know what MCP is
   - Prompting and context is important. At the start of a session, give context of the situation. Do not ask the assistants to adopt personas, be up front that you are an AI and be clear about your expectations. 

5. **Parallel Consultation Pattern**:

   Use parallel tasks when appropriate using the Task tool. 
   ```
   Task 1: o3 (session: "feature-x") - "Best approach for X?"
   Task 2: gemini25_pro - "What are the risks with X?"
   Task 3: gpt4_1 - "Current best practices for X?"
   ```

6. **Quality Control Before Changes**:
   - Get implementation reviewed: "What's genuinely problematic here?"
   - Challenge consensus: "You all favor approach A. What will break?"
   - Verify fixes address root causes, not symptoms

7. **Remember**: You're the responsible agent. The assistants provide perspectives; you synthesize and implement. This is collaborative problem-solving, not approval-seeking.

**ENFORCEMENT**: Using Second Brain is part of your standard development workflow. The only choice is which assistants to consult and what to ask them - not whether to consult them.
</critical_instructions>

## Project Overview

MCP Second-Brain Server - A Model Context Protocol (MCP) server that provides access to multiple AI models (OpenAI o-series and Google Gemini 2.5) with intelligent context management for large codebases. Built with a sophisticated descriptor-based tool system using Python descriptors for parameter routing. Uses FastMCP framework with smart file inlining and vector store integration for RAG. Supports optional multi-turn conversations for OpenAI models.

## Commands

- **Install dependencies**: `uv pip install -e .`
- **Google Cloud auth** (for Gemini): `gcloud auth application-default login`
- **Run server**: `uv run -- mcp-second-brain`
- **Server runs on**: Configurable via HOST/PORT env vars (default: 127.0.0.1:8000)

## Architecture

### Core Components

1. **Adapters** (`mcp_second_brain/adapters/`)
   - `base.py`: Abstract `BaseAdapter` defining the interface
   - `openai_adapter.py`: OpenAI models integration (o3, o3-pro, gpt-4.1) via Responses API
   - `vertex_adapter.py`: Google Vertex AI integration (Gemini 2.5 pro/flash) via google-genai SDK

2. **Tool System** (`mcp_second_brain/tools/`)
   - `descriptors.py`: Route descriptors for parameter routing
   - `base.py`: ToolSpec base class with dataclass-like definitions
   - `definitions.py`: Tool definitions for all models
   - `executor.py`: Orchestrates tool execution with component delegation
   - `integration.py`: FastMCP integration layer

3. **Server** (`mcp_second_brain/server.py`)
   - FastMCP-based MCP protocol implementation
   - Registers dataclass-based tools dynamically
   - Minimal orchestration logic

4. **Context Management** (`mcp_second_brain/utils/`)
   - `fs.py`: Intelligent file gathering with gitignore support and filtering
   - `prompt_builder.py`: Smart context inlining vs vector store routing
   - `vector_store.py`: OpenAI vector store integration for RAG
   - `token_counter.py`: Token counting for context management

### Smart Context Management

- **Files under `MAX_INLINE_TOKENS` (12000)**: Inlined directly into prompt
- **Larger contexts**: Automatic vector store creation for RAG
- **File filtering**: Respects .gitignore, skips binaries, size limits (500KB/file, 50MB total)
- **Extension support**: 60+ text file types, OpenAI vector store compatible formats

### Available Tools

Tools are defined using a descriptor-based system with parameter routing:

Primary tools:
- `chat_with_gemini25_pro`: Deep analysis (Gemini 2.5 Pro, ~1M tokens)
- `chat_with_gemini25_flash`: Fast summarization (Gemini 2.5 Flash, ~1M tokens)
- `chat_with_o3`: Chain-of-thought reasoning (OpenAI o3, ~200k tokens) - supports session_id
- `chat_with_o3_pro`: Formal proofs (OpenAI o3-pro, ~200k tokens) - supports session_id
- `chat_with_gpt4_1`: Large-scale analysis (GPT-4.1, ~1M tokens) - supports session_id

All tools follow the naming pattern `chat_with_{model_name}` for clarity and consistency.

Utility tools:
- `create_vector_store_tool`: Create vector stores for RAG workflows
- `list_models`: Show all available models and capabilities

### Conversation Support

OpenAI tools (o3, o3-pro, gpt-4.1) support optional multi-turn conversations:
- Pass `session_id` parameter to maintain conversation continuity
- Server maintains ephemeral cache (1 hour TTL) of OpenAI response IDs
- No conversation history stored - OpenAI maintains full context
- Gemini models remain single-shot (no session support)

### Configuration

Environment variables (via `.env` file):
- `OPENAI_API_KEY`: Required for OpenAI models (o3, o3-pro, gpt-4.1)
- `VERTEX_PROJECT`, `VERTEX_LOCATION`: Required for Google Vertex AI models
- `HOST`, `PORT`: Server configuration
- `MAX_INLINE_TOKENS`: Context inlining threshold (default: 12000)
- `DEFAULT_TEMPERATURE`: AI model temperature setting
- `LOG_LEVEL`: Logging verbosity

## Second Brain MCP Mandate for Claude

### When You MUST Use Second Brain

Immediately engage Second Brain when encountering these triggers:

1. **Code Analysis Triggers**:
   - Debugging errors with unclear root causes
   - Understanding unfamiliar codebases or frameworks
   - Analyzing performance issues or bottlenecks
   - Reviewing architecture or design patterns

2. **Complexity Triggers**:
   - Tasks requiring analysis of 5+ files
   - Problems with multiple potential solutions
   - Issues spanning different layers of the stack
   - Any request containing "understand", "analyze", "debug", or "optimize"

3. **Context Size Triggers**:
   - Working with files larger than 500 lines
   - Needing to understand relationships across multiple modules
   - When you find yourself reading more than 3 files

### Your Second Brain Workflow

**ALWAYS use parallel execution:**
```
1. Initial analysis with me (Claude)
2. SIMULTANEOUSLY: Second Brain deep dive
3. Synthesize both perspectives for the user
```

**Default Model Selection:**
- First pass: `chat_with_gemini25_flash` (2-3 seconds)
- Need depth: `chat_with_o3` (30-60 seconds)
- Critical issues: `chat_with_o3_pro` (10-30 minutes)

### Why This Makes You More Effective

The Second-Brain server addresses key limitations:

1. **Context Efficiency**: Analyze entire codebases without consuming your context
2. **Specialized Intelligence**: o3-pro for bugs you can't solve, Gemini for multimodal
3. **Parallel Processing**: Get multiple perspectives simultaneously
4. **Better Outcomes**: Catch edge cases and provide more comprehensive solutions

### Your Go-To Patterns

#### Pattern 1: Quick Understanding (< 5 seconds total)
```python
# Run these in PARALLEL:
- You: Read key files and form initial hypothesis
- Second Brain: chat_with_gemini25_flash with full context
- Result: Complete picture in seconds
```

#### Pattern 2: Debugging Mystery (< 2 minutes total)
```python
# When you see an error you don't immediately understand:
- You: Locate error context
- Second Brain: chat_with_o3 with error + surrounding code
- Result: Root cause identified with fix
```

#### Pattern 3: Deep Analysis (background processing)
```python
# For architectural decisions or complex bugs:
- You: Continue working on immediate tasks
- Second Brain: chat_with_o3_pro analyzing in background
- Result: Expert analysis arrives while you stay productive
```

#### Pattern 4: Multi-Model Collaboration
```python
# Get best of all worlds:
- chat_with_gemini25_flash: "What are the main issues?"
- chat_with_o3: "How should we fix issue X?"
- chat_with_gpt4_1: "Find all places this pattern appears"
```

### Decision Tree for Model Selection

```
Is it urgent and needs < 5 second response?
  → chat_with_gemini25_flash

Do you need to search/navigate a large codebase?
  → chat_with_gpt4_1 (best with attachments)

Is it a bug you can't immediately solve?
  → chat_with_o3 (then o3_pro if needed)

Does it involve images/multimodal content?
  → chat_with_gemini25_pro

Is it algorithmic or needs step-by-step reasoning?
  → chat_with_o3

Is it critical and worth waiting 10-30 minutes?
  → chat_with_o3_pro
```

### The Mindset Shift

**Old way**: "Let me analyze this myself first..."
**New way**: "Let me get Second Brain started WHILE I analyze..."

Second Brain isn't a fallback - it's your collaborative partner. Use it proactively, not reactively. The goal is comprehensive understanding in less time, not delegation of work.

### Example: How You Should Behave

**User**: "Can you help me debug why my authentication isn't working?"

**Your immediate response pattern**:
```
"I'll help you debug the authentication issue. Let me analyze the code while also 
getting deeper insights from specialized models."

[In parallel:]
- Read auth-related files
- chat_with_gemini25_flash: "Identify common auth failure points in [context]"
- chat_with_o3: "Debug authentication flow in [specific files]"

"Based on my analysis and Second Brain's insights, I found three potential issues..."
```

This parallel approach typically provides better answers in LESS time than sequential analysis.

### Important: Timeout Configuration

For o3-pro models (chat_with_o3_pro), set timeout to 3600000ms (1 hour) in your MCP config:
```json
"timeout": 3600000
```
These models can take 10-30 minutes to generate responses due to their deep reasoning capabilities.

## Development Notes

- Python 3.10+ required
- Uses `uv` package manager
- FastMCP framework for MCP protocol handling
- Descriptor-based tool system with parameter routing
- All adapters must implement `BaseAdapter.generate()` method
- Tools defined as dataclasses with `@tool` decorator
- Parameters use `Route.prompt()`, `Route.adapter()`, etc. for routing
- **Critical**: Always use absolute paths in context/attachments parameters

## File Paths

**Important**: When using this server, always provide absolute paths in `context` and `attachments` parameters:
- ✅ Correct: `["/Users/username/project/src/"]`
- ❌ Avoid: `["./src/", "../other/"]`

Relative paths will be resolved relative to the MCP server's working directory, not the client's.

## Testing

- **Basic functionality**: Use tools with small context arrays
- **RAG capabilities**: Test with empty context and large attachments arrays
- **File filtering**: Verify .gitignore patterns and binary file exclusion work correctly
- **Parameter routing**: Verify prompt, adapter, vector_store, and session parameters route correctly
- **Multi-turn conversations**: Test session_id continuity with OpenAI models

## Key Dependencies

- `fastmcp`: MCP protocol implementation
- `openai`: OpenAI API client with Responses API support
- `google-genai`: Google Vertex AI client
- `tiktoken`: Token counting
- `lxml`: XML processing for prompts
- `pydantic-settings`: Configuration management
- Python descriptors for parameter routing system
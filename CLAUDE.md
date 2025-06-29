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
   - **gemini25_pro**: Massive context windows (~1M tokens), smart, multi-turn conversations (use session_id)
   - **gemini25_flash**: Massive context windows (~1M tokens), fast, multi-turn conversations (use session_id)
   - **gpt4_1**: Massive context windows (~1M tokens), Web search for current info (use session_id)
   - **IMPORTANT**: None of these assistants are aware of MCP (Model Context Protocol) or the Responses API
   - o3/o3_pro/gemini models have no knowledge of these APIs at all
   - gpt4_1 doesn't know either but can search the web to find information if needed
   - Prompting and context is important. At the start of a session, give context of the situation. Do not ask the assistants to adopt personas, be up front that you are an AI and be clear about your expectations. 

5. **Tasks**
   -Avoid using tasks for calling the assistants. 

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
   - `openai/`: OpenAI models integration (o3, o3-pro, gpt-4.1) via Responses API
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

- **Files within context percentage**: Inlined directly into prompt (default 85% of model's context window minus safety margin)
- **Larger contexts**: Automatic vector store creation for RAG
- **File filtering**: Respects .gitignore, skips binaries, size limits (500KB/file, 50MB total)
- **Extension support**: 60+ text file types, OpenAI vector store compatible formats

### Available Tools

Tools are defined using a descriptor-based system with parameter routing:

Primary tools:
- `chat_with_gemini25_pro`: Deep analysis (Gemini 2.5 Pro, ~1M tokens)
- `chat_with_gemini25_flash`: Fast summarization (Gemini 2.5 Flash, ~1M tokens)
- `chat_with_o3`: Chain-of-thought reasoning (OpenAI o3, ~200k tokens) - supports session_id, **now with web search!**
- `chat_with_o3_pro`: Formal proofs (OpenAI o3-pro, ~200k tokens) - supports session_id, **now with web search!**
- `chat_with_gpt4_1`: Large-scale analysis (GPT-4.1, ~1M tokens) - supports session_id, web search enabled
- `research_with_o3_deep_research`: Ultra-deep research (OpenAI o3-deep-research, ~200k tokens) - supports session_id, autonomous web search, 10-60 min response time
- `research_with_o4_mini_deep_research`: Fast research (OpenAI o4-mini-deep-research, ~200k tokens) - supports session_id, autonomous web search, 2-10 min response time

Tools follow the naming patterns:
- `chat_with_{model_name}` for conversational AI assistance
- `research_with_{model_name}` for autonomous research tools

Utility tools:
- `create_vector_store_tool`: Create vector stores for RAG workflows
- `list_models`: Show all available models and capabilities
- `search_project_memory`: Search past conversations and git commits
- `search_session_attachments`: Search temporary vector stores created from attachments

Use `search_project_memory` whenever you need to recall prior AI decisions or
code history. After uploading files with `create_vector_store_tool`, search them
using `search_session_attachments`.

### Conversation Support

All AI tools now support multi-turn conversations:

**OpenAI models (o3, o3-pro, gpt-4.1, research models)**:
- Pass `session_id` parameter to maintain conversation continuity
- Server maintains ephemeral cache (1 hour TTL) of OpenAI response IDs
- No conversation history stored - OpenAI maintains full context
- Research models (o3-deep-research, o4-mini-deep-research) also support sessions

**Gemini models (gemini-2.5-pro, gemini-2.5-flash)**:
- Require `session_id` parameter for multi-turn conversations
- Full conversation history stored locally in SQLite
- Same TTL and cache management as OpenAI models
- Each exchange (user + assistant messages) is persisted

### Configuration

Environment variables (via `.env` file):
- `OPENAI_API_KEY`: Required for OpenAI models (o3, o3-pro, gpt-4.1)
- `VERTEX_PROJECT`, `VERTEX_LOCATION`: Required for Google Vertex AI models
- `HOST`, `PORT`: Server configuration
- `CONTEXT_PERCENTAGE`: Percentage of model context to use (default: 0.85 = 85%)
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

**Use parallel execution (Task tool) when appropriate:**
```
1. Initial analysis with me (Claude)
2. SIMULTANEOUSLY: Second Brain deep dive
3. Synthesize both perspectives for the user
```

**Default Model Selection:**
- Finding simple information (stuff context with as much as you can): `chat_with_gemini25_flash` (2-3 seconds)
- Need depth: `chat_with_o3` (10-30 seconds)
- Critical issues: `chat_with_o3_pro` (5-10 minutes)

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

Do you need current information or web research?
  → chat_with_o3 / chat_with_o3_pro (now with web search!)
  → research_with_o3_deep_research (for comprehensive research, 10-60 min)
  → research_with_o4_mini_deep_research (for quick research, 2-10 min)

Is it a bug you can't immediately solve?
  → chat_with_o3 (then o3_pro if needed)

Does it involve images/multimodal content?
  → chat_with_gemini25_pro

Is it algorithmic or needs step-by-step reasoning?
  → chat_with_o3

Is it critical and worth waiting 10-30 minutes?
  → chat_with_o3_pro

Need ultra-deep research with web search?
  → research_with_o3_deep_research (most thorough, 10-60 min)
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

For deep reasoning models, set appropriate timeouts in your MCP config:
- `chat_with_o3_pro`: Set timeout to 3600000ms (1 hour) - can take 10-30 minutes
- `research_with_o3_deep_research`: Set timeout to 3600000ms (1 hour) - can take 10-60 minutes
- `research_with_o4_mini_deep_research`: Set timeout to 900000ms (15 min) - can take 2-10 minutes

```json
"timeout": 3600000
```

These models perform extensive reasoning and web research, requiring longer processing times.

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

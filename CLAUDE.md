# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
- `vertex_gemini25_pro`: Deep analysis (Gemini 2.5 Pro, ~1M tokens)
- `vertex_gemini25_flash`: Fast summarization (Gemini 2.5 Flash, ~1M tokens)
- `open_aio3_reasoning`: Chain-of-thought reasoning (OpenAI o3, ~200k tokens) - supports session_id
- `open_aio3_pro_deep_analysis`: Formal proofs (OpenAI o3-pro, ~200k tokens) - supports session_id
- `open_aigpt4_long_context`: Large-scale analysis (GPT-4.1, ~1M tokens) - supports session_id

Aliases for backward compatibility:
- `deep-multimodal-reasoner` → `vertex_gemini25_pro`
- `flash-summary-sprinter` → `vertex_gemini25_flash`
- `chain-of-thought-helper` → `open_aio3_reasoning`
- `slow-and-sure-thinker` → `open_aio3_pro_deep_analysis`
- `fast-long-context-assistant` → `open_aigpt4_long_context`

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

## Usage Patterns and When to Use Second-Brain

### Why Use MCP Second-Brain?

The Second-Brain server addresses key limitations when working with Claude:

1. **Context Limitations**: Claude's context window gets consumed quickly with large codebases
2. **Model Diversity**: Access to specialized models (o3-pro for deep reasoning, Gemini for multimodal)
3. **Speed vs Intelligence**: Choose the right tool for each task phase
4. **RAG Capabilities**: Semantic search across large document sets

### Recommended Chaining Workflows

#### Complex Debugging Pattern
```
1. Capture verbose output → save to file
2. open_aigpt4_long_context → identify key files (context: output + large codebase)
3. open_aio3_pro_deep_analysis → deep analysis (context: key files, attachments: full codebase)
```

#### Multi-Turn Debugging Session
```
1. open_aio3_reasoning (session_id: "debug-123") → initial analysis
2. open_aio3_reasoning (session_id: "debug-123") → follow-up questions
3. open_aio3_pro_deep_analysis (session_id: "debug-123") → deep dive into specific issue
```

#### Performance Analysis Pattern
```
1. vertex_gemini25_flash → quick bottleneck identification
2. vertex_gemini25_pro → comprehensive analysis with optimization strategies
```

#### Code Architecture Review
```
1. open_aigpt4_long_context → overall structure analysis
2. open_aio3_reasoning → design pattern evaluation
3. open_aio3_pro_deep_analysis → formal architecture recommendations
```

### When to Use Each Tool

- **vertex_gemini25_flash**: Initial triage, quick summaries, fast insights
- **open_aigpt4_long_context**: Code navigation, file identification, large-scale refactoring
- **vertex_gemini25_pro**: Bug fixing, complex reasoning, multimodal analysis
- **open_aio3_reasoning**: Algorithm design, step-by-step problem solving
- **open_aio3_pro_deep_analysis**: When you need maximum intelligence, formal proofs, complex debugging

### Important: Timeout Configuration

For o3-pro models (open_aio3_pro_deep_analysis), set timeout to 3600000ms (1 hour) in your MCP config:
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
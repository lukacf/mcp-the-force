# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP Second-Brain Server - A Model Context Protocol (MCP) server that provides access to multiple AI models (OpenAI o-series and Google Gemini 2.5) with intelligent context management for large codebases. Uses FastMCP framework with smart file inlining and vector store integration for RAG.

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

2. **Server** (`mcp_second_brain/server.py`)
   - FastMCP-based MCP protocol implementation
   - Exposes 5 AI tools with different model specializations
   - Lazy adapter initialization for better error handling

3. **Context Management** (`mcp_second_brain/utils/`)
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

Each tool is exposed via MCP protocol with specific use cases:
- `deep-multimodal-reasoner`: Bug fixing, complex reasoning (Gemini 2.5 Pro, ~2M tokens)
- `flash-summary-sprinter`: Fast summarization (Gemini 2.5 Flash, ~2M tokens)
- `chain-of-thought-helper`: Algorithm design (OpenAI o3, ~200k tokens)
- `slow-and-sure-thinker`: Formal proofs, deep analysis (OpenAI o3-pro, ~200k tokens)
- `fast-long-context-assistant`: Large-scale refactoring (OpenAI gpt-4.1, ~1M tokens)

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
2. fast-long-context-assistant → identify key files (context: output + large codebase)
3. slow-and-sure-thinker → deep analysis (context: key files, attachments: full codebase)
```

#### Performance Analysis Pattern
```
1. flash-summary-sprinter → quick bottleneck identification
2. deep-multimodal-reasoner → comprehensive analysis with optimization strategies
```

#### Code Architecture Review
```
1. fast-long-context-assistant → overall structure analysis
2. chain-of-thought-helper → design pattern evaluation
3. slow-and-sure-thinker → formal architecture recommendations
```

### When to Use Each Tool

- **flash-summary-sprinter**: Initial triage, quick summaries, fast insights
- **fast-long-context-assistant**: Code navigation, file identification, large-scale refactoring
- **deep-multimodal-reasoner**: Bug fixing, complex reasoning, multimodal analysis
- **chain-of-thought-helper**: Algorithm design, step-by-step problem solving
- **slow-and-sure-thinker**: When you need maximum intelligence, formal proofs, complex debugging

## Development Notes

- Python 3.10+ required
- Uses `uv` package manager
- FastMCP framework for MCP protocol handling
- Pydantic with pydantic-settings for configuration
- All adapters must implement `BaseAdapter.generate()` method
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

## Key Dependencies

- `fastmcp`: MCP protocol implementation
- `openai`: OpenAI API client with Responses API support
- `google-genai`: Google Vertex AI client
- `tiktoken`: Token counting
- `lxml`: XML processing for prompts
- `pydantic-settings`: Configuration management
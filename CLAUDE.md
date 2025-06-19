# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP Second-Brain Server - A Model Context Protocol (MCP) server that provides access to multiple AI models (OpenAI o-series and Google Gemini 2.5) with intelligent context management for large codebases.

## Commands

- **Install dependencies**: `uv pip install -e .`
- **Run server**: `uv run -- mcp-second-brain`
- **Server runs on**: Configurable via HOST/PORT env vars (default: 127.0.0.1:8000)

## Architecture

### Core Components

1. **Adapters** (`src/mcp_second_brain/adapters/`)
   - `base.py`: Abstract `BaseAdapter` defining the interface
   - `openai.py`: OpenAI models integration (o3, o3-pro, gpt-4.1)
   - `vertex.py`: Google Vertex AI integration (Gemini 2.5 pro/flash)

2. **Server** (`src/mcp_second_brain/server.py`)
   - FastAPI-based MCP protocol implementation
   - Exposes 5 AI tools with different model specializations
   - Handles token counting and context management

3. **Token Management**
   - Files under `MAX_INLINE_TOKENS` (12000) are inlined directly
   - Larger contexts trigger automatic vector store creation
   - Token counting prevents exceeding model limits

### Available Tools

Each tool is exposed via MCP protocol with specific use cases:
- `deep-multimodal-reasoner`: Bug fixing, complex reasoning (Gemini 2.5 Pro)
- `flash-summary-sprinter`: Fast summarization (Gemini 2.5 Flash)
- `chain-of-thought-helper`: Algorithm design (OpenAI o3)
- `slow-and-sure-thinker`: Formal proofs, deep analysis (OpenAI o3-pro)
- `fast-long-context-assistant`: Large-scale refactoring (GPT-4.1)

### Configuration

Environment variables (via `.env` file):
- `OPENAI_API_KEY`: Required for OpenAI models
- `ANTHROPIC_API_KEY`: Required for Anthropic models
- `HOST`, `PORT`: Server configuration
- `LOG_LEVEL`: Logging verbosity
- Model-specific settings in `src/mcp_second_brain/config.py`

## Development Notes

- Python 3.10+ required
- Uses `uv` package manager
- Pydantic for data validation and settings
- FastAPI async endpoints for MCP protocol handling
- All adapters must implement `BaseAdapter.process()` method
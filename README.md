# MCP Second‑Brain Server

Launches a local MCP server that proxies requests to OpenAI o‑series or
Google Gemini 2.5, safely attaching large repos through a vector store.

## Quick Start

```bash
uv pip install -e .
uv run -- mcp-second-brain
```

## Important: Use Absolute Paths

When using the MCP tools, always provide **absolute paths** in the `context` and `attachments` parameters for reliable results:

✅ **Correct:**
```json
{
  "instructions": "Analyze this codebase",
  "output_format": "summary", 
  "context": ["/Users/username/my-project/src/"]
}
```

❌ **Avoid:**
```json
{
  "instructions": "Analyze this codebase",
  "output_format": "summary",
  "context": ["./src/", "../other-project/"]
}
```

Relative paths will be resolved relative to the MCP server's working directory, which may not match your expectation.

## Available Tools

- **deep-multimodal-reasoner**: Bug fixing, complex reasoning (Gemini 2.5 Pro)
- **flash-summary-sprinter**: Fast summarization (Gemini 2.5 Flash)  
- **chain-of-thought-helper**: Algorithm design (OpenAI o3)
- **slow-and-sure-thinker**: Formal proofs, deep analysis (OpenAI o3-pro)
- **fast-long-context-assistant**: Large-scale refactoring (OpenAI gpt-4.1)
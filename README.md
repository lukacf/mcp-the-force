# MCP Second‑Brain Server

An intelligent Model Context Protocol (MCP) server that orchestrates multiple AI models with advanced context management for large codebases. Supports both OpenAI (o3, o3-pro, gpt-4.1) and Google Gemini (2.5-pro, 2.5-flash) models with smart file inlining and vector store integration.

## 🚀 Quick Start

```bash
# Install dependencies
uv pip install -e .

# Set up Google Cloud authentication (for Gemini models)
gcloud auth application-default login

# Configure environment variables
cp .env.example .env
# Edit .env with your API keys

# Run the server
uv run -- mcp-second-brain
```

## 🔧 Configuration

### Environment Variables
Create a `.env` file with your API credentials:

```env
OPENAI_API_KEY=your_openai_api_key_here
VERTEX_PROJECT=your_gcp_project_id
VERTEX_LOCATION=your_gcp_location
HOST=127.0.0.1
PORT=8000
MAX_INLINE_TOKENS=12000
DEFAULT_TEMPERATURE=0.2
```

### Model Configuration
Models are configured in `mcp_second_brain/config/models.yaml`. To add a new model, simply add an entry:

```yaml
- id: your_provider_model_capability
  provider: your_provider
  adapter: adapter_name
  model_name: actual-model-name
  description: What this model excels at
  context_window: 200000
  default_timeout: 600
  supports_session: true
  supports_vector_store: true
```

## 🛠️ Available Tools

The server dynamically generates tools from configuration. All tool names follow the pattern: `{provider}_{model}_{capability}`.

### Primary Tools

| Tool Name | Model | Purpose | Context | Session Support |
|-----------|-------|---------|---------|------------------|
| `vertex_gemini25_pro_multimodal` | Gemini 2.5 Pro | Deep multimodal analysis, bug fixing | ~2M tokens | ❌ |
| `vertex_gemini25_flash_summary` | Gemini 2.5 Flash | Fast summarization, quick insights | ~2M tokens | ❌ |
| `openai_o3_reasoning` | OpenAI o3 | Chain-of-thought reasoning, algorithms | ~200k tokens | ✅ |
| `openai_o3_pro_deep_analysis` | OpenAI o3-pro | Formal proofs, complex debugging | ~200k tokens | ✅ |
| `openai_gpt4_longcontext` | GPT-4.1 | Large-scale refactoring, RAG workflows | ~1M tokens | ✅ |

### Legacy Aliases (for backward compatibility)

- `deep-multimodal-reasoner` → `vertex_gemini25_pro_multimodal`
- `flash-summary-sprinter` → `vertex_gemini25_flash_summary`
- `chain-of-thought-helper` → `openai_o3_reasoning`
- `slow-and-sure-thinker` → `openai_o3_pro_deep_analysis`
- `fast-long-context-assistant` → `openai_gpt4_longcontext`

### Additional Tools

- `create_vector_store_tool` - Create vector stores for RAG workflows
- `list_models` - List all available models and their capabilities

## 📁 Smart Context Management

The server intelligently handles large codebases through a two-tier approach:

### 🔄 **Inline Context** (Fast Access)
- Files under 12,000 tokens (configurable) are embedded directly in the prompt
- Provides immediate access for small to medium projects
- Optimized for quick analysis and focused tasks

### 🔍 **Vector Store/RAG** (Large Projects)
- Files exceeding the inline limit are uploaded to OpenAI vector stores
- Enables semantic search across extensive codebases
- Perfect for enterprise projects and comprehensive analysis

### 🎯 **Intelligent File Filtering**
- **Respects `.gitignore`**: Automatically excludes ignored files
- **Skip common directories**: `node_modules`, `__pycache__`, `.git`, etc.
- **Text file detection**: Smart binary vs text identification
- **Size limits**: 500KB per file, 50MB total maximum
- **Extension filtering**: Supports 60+ text file formats

## 💬 Conversation Support (NEW)

OpenAI models (o3, o3-pro, gpt-4.1) now support multi-turn conversations through a simple `session_id` parameter:

### Basic Usage
```json
{
  "tool": "openai_o3_reasoning",
  "session_id": "debug-session-123",
  "instructions": "Analyze this function",
  "output_format": "explanation",
  "context": ["/path/to/file.py"]
}
```

Follow-up in the same session:
```json
{
  "tool": "openai_o3_reasoning", 
  "session_id": "debug-session-123",
  "instructions": "Now optimize it for performance",
  "output_format": "code",
  "context": ["/path/to/file.py"]
}
```

### How It Works
- The server maintains a lightweight ephemeral cache (1 hour TTL)
- Only stores the `previous_response_id` from OpenAI's Responses API
- No conversation history is stored - OpenAI maintains the full context
- Sessions expire automatically after 1 hour of inactivity
- Gemini models remain single-shot (no session support)

### Vector Store Management
Create persistent vector stores for RAG:
```json
{
  "tool": "create_vector_store_tool",
  "files": ["/path/to/docs/", "/path/to/src/"],
  "name": "project-knowledge-base"
}
```

Then use the returned `vector_store_id` with any OpenAI tool by passing it in the `attachments` parameter.

## 📖 Usage Examples

### When to Use MCP Second-Brain

The Second-Brain server is designed to overcome Claude's context limitations and provide access to more specialized AI models. Use it when:

- **Context Overflow**: Your codebase is too large for Claude's context window
- **Need Specialized Models**: Tasks requiring o3-pro's deep reasoning or Gemini's multimodal capabilities  
- **Speed vs Intelligence Trade-offs**: Fast analysis followed by deep reasoning
- **RAG Requirements**: Semantic search across large document sets

### Multi-Stage Debugging Workflow

Here's a powerful chaining pattern for complex debugging:

#### Step 1: Capture Verbose Output
```bash
# Run failing tests with maximum verbosity
npm test --verbose --reporter=verbose > test_output.log 2>&1
```

#### Step 2: Fast Triage with Long Context
```json
{
  "tool": "fast-long-context-assistant",
  "instructions": "Analyze the test failures and identify the 3-5 most critical files that likely contain the root cause",
  "output_format": "prioritized list with file paths and reasoning",
  "context": ["/Users/username/project/test_output.log"],
  "attachments": ["/Users/username/project/src/", "/Users/username/project/tests/"]
}
```

#### Step 3: Deep Analysis with o3-pro
```json
{
  "tool": "slow-and-sure-thinker", 
  "instructions": "Perform deep root cause analysis of the test failures. Provide specific fix recommendations with code changes.",
  "output_format": "detailed technical analysis with fix proposals",
  "reasoning_effort": "high",
  "context": [
    "/Users/username/project/src/auth/core.py",
    "/Users/username/project/src/database/connection.py", 
    "/Users/username/project/tests/auth_test.py"
  ],
  "attachments": ["/Users/username/project/"]
}
```

### Basic Analysis
```json
{
  "instructions": "Analyze this codebase and identify potential security issues",
  "output_format": "structured report with recommendations", 
  "context": ["/Users/username/my-project/src/"]
}
```

### RAG-Enhanced Analysis (Large Codebases)
```json
{
  "instructions": "How do I add a new authentication method to this system?",
  "output_format": "step-by-step implementation guide",
  "context": [],
  "attachments": ["/Users/username/large-project/"]
}
```

### Performance Investigation Chain
```json
{
  "tool": "flash-summary-sprinter",
  "instructions": "Identify performance bottlenecks in this React application",
  "output_format": "quick summary of potential issues",
  "context": ["/Users/username/react-app/src/"]
}
```

Then follow up with:
```json
{
  "tool": "deep-multimodal-reasoner", 
  "instructions": "Deep dive into the identified performance issues. Analyze render patterns, state updates, and provide optimization strategies.",
  "output_format": "comprehensive performance audit with actionable fixes",
  "context": ["/Users/username/react-app/src/components/Dashboard.tsx"],
  "attachments": ["/Users/username/react-app/"]
}
```

## ⚠️ Important: Use Absolute Paths

Always provide **absolute paths** in `context` and `attachments` parameters:

✅ **Correct:**
```json
{
  "context": ["/Users/username/my-project/src/"],
  "attachments": ["/Users/username/docs/"]
}
```

❌ **Avoid:**
```json
{
  "context": ["./src/", "../other-project/"],
  "attachments": ["./docs/"]
}
```

Relative paths will be resolved relative to the MCP server's working directory, which may not match your expectation.

## 🔌 MCP Integration

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "second-brain": {
      "command": "uv",
      "args": ["run", "--", "mcp-second-brain"],
      "env": {
        "OPENAI_API_KEY": "your_openai_api_key_here",
        "VERTEX_PROJECT": "your_gcp_project_id",
        "VERTEX_LOCATION": "your_gcp_location"
      },
      "timeout": 3600000
    }
  }
}
```

**Important**: Set `timeout` to 3600000 (1 hour) for o3-pro models which can take 10-30 minutes to respond.

## 🏗️ Architecture

### Core Components
- **Server**: FastMCP-based MCP protocol implementation
- **Adapters**: Pluggable AI model integrations (OpenAI, Vertex AI)
- **Context Manager**: Smart file gathering and token management
- **Vector Store**: RAG integration for large document sets

### File Processing Pipeline
1. **Path Resolution**: Convert relative to absolute paths
2. **File Discovery**: Recursive directory scanning with filtering
3. **Content Analysis**: Text vs binary detection
4. **Token Counting**: Efficient context management
5. **Routing Decision**: Inline vs vector store based on size
6. **AI Processing**: Model-specific prompt formatting and execution

## 🧪 Testing RAG Capabilities

To test the vector store functionality:

```json
{
  "instructions": "Explain the complete architecture of this system",
  "output_format": "comprehensive technical documentation",
  "context": [],
  "attachments": ["/absolute/path/to/large/codebase/"]
}
```

The system will automatically upload supported files (.py, .js, .md, .json, .txt, etc.) to a vector store and enable semantic search across the entire codebase.

## 📚 Supported File Types

### For Inline Context
All text files detected by the smart filtering system including source code, documentation, configuration files, and more.

### For Vector Store (RAG)
OpenAI-supported formats: `.c`, `.cpp`, `.css`, `.csv`, `.doc`, `.docx`, `.go`, `.html`, `.java`, `.js`, `.json`, `.md`, `.pdf`, `.php`, `.py`, `.rb`, `.tex`, `.ts`, `.txt`, `.xml`, `.zip` and more.

## 🔧 Extending the System

To add a new AI model adapter:

1. **Create adapter class** inheriting from `BaseAdapter`
2. **Implement `generate()` method** with model-specific logic
3. **Add configuration** variables in `config.py`
4. **Register in server.py** with a new tool function
5. **Update imports** in `adapters/__init__.py`

See the existing `OpenAIAdapter` and `VertexAdapter` classes for reference implementations.

## 📄 License

Private repository - see license terms.
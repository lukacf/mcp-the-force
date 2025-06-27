# MCP Second‑Brain Server

An intelligent Model Context Protocol (MCP) server that orchestrates multiple AI models with advanced context management for large codebases. Built with a sophisticated descriptor-based tool system, it supports both OpenAI (o3, o3-pro, gpt-4.1) and Google Gemini (2.5-pro, 2.5-flash) models with smart file inlining and vector store integration.

## 🚀 Quick Start

```bash
# Install dependencies
uv pip install -e .

# Set up Google Cloud authentication (for Gemini models)
# See docs/authentication-guide.md for all authentication options
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
CONTEXT_PERCENTAGE=0.85
DEFAULT_TEMPERATURE=0.2
```

### Logging and Secret Redaction
The server installs a `SecretRedactionFilter` that automatically replaces any
`sk-` style keys and values of environment variables ending with `_KEY` or
`_SECRET` with `[REDACTED]` before they are written to the log files.

### Google Cloud Authentication

The server requires Google Cloud authentication for Gemini models. See [docs/authentication-guide.md](docs/authentication-guide.md) for detailed setup instructions.

**Recommended methods:**
- **Development**: Use `gcloud auth application-default login`
- **Production**: Use service accounts with proper IAM roles
- **CI/CD**: Use Workload Identity Federation (no stored secrets)

The server uses Google's Application Default Credentials (ADC) discovery, automatically finding credentials in standard locations.

### Architecture Overview

The server uses a descriptor-based tool system that provides:
- **Type-safe parameter routing** to different subsystems (prompt, adapter, vector_store, session)
- **Automatic validation** of inputs with helpful error messages
- **Custom prompt templates** per model for optimal performance
- **Dynamic tool generation** from Python dataclasses

### Parameter Routing

Each parameter is automatically routed to the appropriate subsystem:

| Parameter | Route | Purpose | Example |
|-----------|-------|---------|---------|
| `instructions` | prompt | Main task description | `"Analyze this function"` |
| `output_format` | prompt | Expected response format | `"Brief summary"` |
| `context` | prompt | Files to inline in prompt | `["/path/to/file.py"]` |
| `temperature` | adapter | Model creativity (0-1) | `0.7` |
| `reasoning_effort` | adapter | o3/o3-pro reasoning depth | `"high"` |
| `attachments` | vector_store | Files for RAG search | `["/large/codebase/"]` |
| `session_id` | session | Conversation continuity | `"debug-123"` |

## 🛠️ Available Tools

The server provides tools defined through a descriptor-based system. Each tool has specific parameters routed to different subsystems for optimal processing.

### Primary Tools

| Tool Name | Model | Purpose | Context | Session Support |
|-----------|-------|---------|---------|------------------|
| `chat_with_gemini25_pro` | Gemini 2.5 Pro | Deep multimodal analysis, bug fixing | ~1M tokens | ❌ |
| `chat_with_gemini25_flash` | Gemini 2.5 Flash | Fast summarization, quick insights | ~1M tokens | ❌ |
| `chat_with_o3` | OpenAI o3 | Chain-of-thought reasoning, algorithms | ~200k tokens | ✅ |
| `chat_with_o3_pro` | OpenAI o3-pro | Formal proofs, complex debugging | ~200k tokens | ✅ |
| `chat_with_gpt4_1` | GPT-4.1 | Large-scale refactoring, RAG workflows | ~1M tokens | ✅ |

### Tool Naming Convention

All tools follow the pattern `chat_with_{model_name}` for clarity and consistency. This makes it clear that these tools enable chatting with specific AI models.

### Additional Tools

- `create_vector_store_tool` - Create vector stores for RAG workflows
- `list_models` - List all available models and their capabilities

## 📁 Smart Context Management

The server intelligently handles large codebases through a two-tier approach:

### 🔄 **Inline Context** (Fast Access)
- Files within context percentage (default 85% of model limit minus safety margin) are embedded directly in the prompt
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

Call tools with their specific parameters:

```python
# Example using the MCP protocol
result = await mcp.call_tool(
    "chat_with_o3",
    instructions="Analyze this function for potential bugs",
    output_format="detailed analysis with recommendations",
    context=["/path/to/file.py"],
    reasoning_effort="medium",  # Optional: low, medium, high
    session_id="debug-session-123"  # Required for OpenAI models
)
```

Follow-up in the same session:

```python
# The session remembers previous context
result = await mcp.call_tool(
    "chat_with_o3",
    instructions="Now optimize it for performance based on the issues we found",
    output_format="optimized code with explanations",
    context=["/path/to/file.py"],
    session_id="debug-session-123"  # Same session ID continues conversation
)
```

### How It Works
- The server maintains a lightweight ephemeral cache (1 hour TTL)
- Only stores the `previous_response_id` from OpenAI's Responses API
- No conversation history is stored - OpenAI maintains the full context
- Sessions expire automatically after 1 hour of inactivity
- Gemini models remain single-shot (no session support)

### Vector Store Management

Create persistent vector stores for RAG:

```python
# Create a vector store from your codebase
result = await mcp.call_tool(
    "create_vector_store_tool",
    files=["/path/to/docs/", "/path/to/src/"],
    name="project-knowledge-base"
)
# Returns: {"vector_store_id": "vs_...", "status": "created"}
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

```python
# Use GPT-4.1 for fast analysis of large contexts
result = await mcp.call_tool(
    "chat_with_gpt4_1",
    instructions="Analyze the test failures and identify the 3-5 most critical files that likely contain the root cause",
    output_format="prioritized list with file paths and reasoning",
    context=["/Users/username/project/test_output.log"],
    attachments=["/Users/username/project/src/", "/Users/username/project/tests/"],
    temperature=0.3  # Lower temperature for more focused analysis
)
```

#### Step 3: Deep Analysis with o3-pro

```python
# Use o3-pro for deep reasoning (can take 10-30 minutes)
result = await mcp.call_tool(
    "chat_with_o3_pro",
    instructions="Perform deep root cause analysis of the test failures. Provide specific fix recommendations with code changes.",
    output_format="detailed technical analysis with fix proposals",
    reasoning_effort="high",  # Maximum reasoning effort
    max_reasoning_tokens=100000,  # Allow extensive reasoning
    context=[
        "/Users/username/project/src/auth/core.py",
        "/Users/username/project/src/database/connection.py", 
        "/Users/username/project/tests/auth_test.py"
    ],
    attachments=["/Users/username/project/"]
)
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
  "tool": "chat_with_gemini25_flash",
  "instructions": "Identify performance bottlenecks in this React application",
  "output_format": "quick summary of potential issues",
  "context": ["/Users/username/react-app/src/"]
}
```

Then follow up with:
```json
{
  "tool": "chat_with_gemini25_pro", 
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

### Descriptor-Based Tool System

The server uses a sophisticated descriptor-based architecture:

```python
@tool
class ChatWithO3(ToolSpec):
    """Chain-of-thought reasoning and algorithm design."""
    
    # Model configuration
    model_name = "o3"
    adapter_class = "openai"
    context_window = 200_000
    
    # Parameters with routing descriptors
    instructions: str = Route.prompt(pos=0)
    output_format: str = Route.prompt(pos=1)
    context: List[str] = Route.prompt(pos=2)
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = Route.adapter()
    session_id: Optional[str] = Route.session()
```

### Core Components
- **Tool Definitions**: Dataclass-like specifications with parameter routing
- **Parameter Router**: Routes parameters to appropriate handlers (prompt, adapter, vector_store, session)
- **Adapters**: Model-specific integrations (OpenAI, Vertex AI)
- **Vector Store Manager**: Handles RAG lifecycle for large contexts
- **Session Manager**: Maintains conversation continuity for supported models

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

### Adding a New Tool

Create a new tool by defining a class with the `@tool` decorator:

```python
@tool
class ChatWithMyModel(ToolSpec):
    """Description of what this tool does."""
    
    # Model configuration
    model_name = "gpt-4"
    adapter_class = "openai"
    context_window = 100_000
    timeout = 300
    
    # Define parameters with routing
    instructions: str = Route.prompt(pos=0, description="Task instructions")
    output_format: str = Route.prompt(pos=1)
    context: List[str] = Route.prompt(pos=2)
    temperature: float = Route.adapter(default=0.7)
    session_id: Optional[str] = Route.session()
```

### Adding a New Adapter

1. Create adapter class inheriting from `BaseAdapter`
2. Implement the `generate()` method
3. Add configuration in environment variables
4. Register adapter class in the tool definition

See `OpenAIAdapter` and `VertexAdapter` for reference implementations.

## 🛠️ Development

### Setting Up Pre-commit Hooks

We use pre-commit hooks to ensure code quality before commits reach CI:

```bash
# Install development dependencies
uv pip install -e ".[dev]"

# Install pre-commit hooks
make install-hooks
# or manually: pre-commit install && pre-commit install --hook-type pre-push
```

**What runs automatically:**
- **On every commit** (fast, <15 seconds):
  - Ruff linting and formatting
  - MyPy type checking
  - Fast unit tests (excluding slow/integration tests)
- **On push** (optional, can skip with `--no-verify`):
  - Full unit test suite

### Development Commands

```bash
make help              # Show all available commands
make lint              # Run ruff and mypy
make test              # Run fast unit tests only
make test-all          # Run all tests (unit + integration + e2e)
make test-unit         # Run all unit tests with coverage
make test-integration  # Run integration tests
make ci                # Run full CI suite locally
make clean             # Clean up generated files
```

### Running Tests

```bash
# Fast feedback loop (what pre-commit runs)
make test

# Full test suite
make test-all

# Specific test types
pytest tests/unit -v                    # All unit tests
pytest tests/unit -m "not slow"         # Fast unit tests only
pytest tests/integration_mcp -v         # MCP integration tests
```

## 📚 Documentation

- [Authentication Guide](docs/authentication-guide.md) - Detailed Google Cloud authentication setup
- [Claude Integration Guide](docs/claude-integration-guide.md) - Best practices for Claude to use Second Brain MCP effectively
- [E2E Test Setup](docs/e2e-test-setup.md) - End-to-end testing configuration
- [GitHub Secrets Setup](docs/github-secrets-setup.md) - CI/CD configuration
- [Workload Identity Setup](docs/workload-identity-setup.md) - Secure authentication for GitHub Actions

## 📄 License

Private repository - see license terms

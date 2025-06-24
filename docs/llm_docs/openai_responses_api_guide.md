# OpenAI Responses API: Comprehensive Guide for LLMs

## Table of Contents
1. [Overview](#overview)
2. [Key Features](#key-features)
3. [API Endpoint and Authentication](#api-endpoint-and-authentication)
4. [Request Parameters](#request-parameters)
5. [Response Structure](#response-structure)
6. [Python SDK Implementation](#python-sdk-implementation)
7. [Advanced Features](#advanced-features)
8. [Error Handling](#error-handling)
9. [Best Practices](#best-practices)
10. [Complete Examples](#complete-examples)

## Overview

The OpenAI Responses API is a powerful next-generation interface that evolves from the Chat Completions API while incorporating advanced capabilities similar to the Assistants API. It's designed to streamline the development of agentic applications by allowing developers to build sophisticated AI agents that can perform complex, multi-step tasks efficiently.

**Important**: For production applications, always pin to specific model snapshots (e.g., `gpt-4.1-2025-04-14`) rather than using version aliases to ensure consistent behavior as models are updated.

### Key Differentiators from Chat Completions API:
- **Built-in tools**: Web search, file search, code interpreter, image generation, and computer use capabilities
- **Stateful conversations**: Maintain context across interactions using `previous_response_id`
- **Background processing**: Handle long-running tasks asynchronously
- **Reasoning models**: Support for advanced models like o3 and o3-pro with configurable reasoning effort
- **Reasoning summaries**: Get insights into the model's thought process
- **Reusable prompts**: Use dashboard-managed prompt templates with variables
- **Enhanced message roles**: Developer role for higher-priority system instructions
- **Vision capabilities**: Analyze images with configurable detail levels

## Key Features

### 1. Built-in Tools

The Responses API includes several powerful built-in tools:

#### Web Search (`web_search_preview`)
- Enables real-time internet searches
- Access up-to-date information beyond the model's training cutoff
- Automatically retrieves and processes web content
- Supports user location and search context size customization

#### File Search (`file_search`)
- Semantic search across user-uploaded documents via vector stores
- Supports various file formats (PDF, DOCX, TXT, etc.)
- Requires creating a vector store and uploading files first
- Enables models to reference specific information from provided files

#### Code Interpreter (`code_interpreter`)
- Execute Python code in a sandboxed container environment
- Generate visualizations and analyze data
- Create and manipulate files programmatically
- Requires container configuration (auto or explicit)

#### Image Generation (`image_generation`)
- Generate images using text prompts and optional image inputs
- Leverages GPT Image model for contextual understanding
- Returns base64-encoded images
- Supports various image parameters (size, quality, etc.)

#### Remote MCP (`mcp`)
- Connect to Model Context Protocol servers
- Extend model capabilities with custom tools hosted by third parties
- Requires server URL and configuration
- **Security Warning**: Only use trusted MCP servers as they can access and potentially exfiltrate any data in the model's context
- Supports filtering tools with `allowed_tools` parameter

#### Computer Use (`computer_use`)
- Create agentic workflows that enable a model to control a computer interface
- Execute automation tasks through browser and desktop interactions
- Take screenshots, click elements, type text, and navigate applications
- Useful for web automation, testing, and data extraction tasks
- Requires specific configuration and security considerations

### 2. Advanced Reasoning Models

The API supports specialized reasoning models optimized for complex problem-solving:

- **o3**: Advanced chain-of-thought reasoning model (~200k context)
- **o3-pro**: Deep analysis and formal reasoning (~200k context, 10-30 min processing)
- **o4-mini**: Faster, more affordable reasoning model (~200k context, optimized for coding/visual tasks)
- **gpt-4o**: General-purpose model with tool capabilities (~200k context)
- **gpt-4.1**: General-purpose model with large context window (~1M context)
- **gpt-4.1-mini**: Balanced for intelligence, speed, and cost (~1M context)
- **gpt-4.1-nano**: Lightweight version with some limitations (no web search, may call same tool multiple times with parallel_tool_calls)
- **codex-mini-latest**: Fast reasoning model optimized for the Codex CLI (~200k context)
### 3. Stateful Conversations

The Responses API provides two ways to manage conversation state:

1. **Manual State Management**: Include previous messages in the `input` array
2. **Automatic State Management**: Use `previous_response_id` to chain responses

Both approaches maintain full conversation context across multiple API calls. Response objects are stored for 30 days by default (disable with `store: false`).

### 4. Background Processing

Handle long-running tasks asynchronously with the `background` parameter, preventing timeouts and improving user experience for complex computations.

## API Endpoint and Authentication

### Endpoint
```
POST https://api.openai.com/v1/responses
```

### Headers
```python
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}
```

### Python SDK Setup
```bash
pip install openai
```

```python
from openai import OpenAI

# Initialize client
client = OpenAI(api_key="your-api-key")

# Or use environment variable
# export OPENAI_API_KEY='your-api-key'
client = OpenAI()
```

## Request Parameters

### Core Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Model to use (e.g., "gpt-4o", "gpt-4.1", "o3", "o4-mini", "codex-mini-latest") |
| `input` | string/array | Yes | Simple prompt (string) or conversation history (array of message objects) |
| `instructions` | string | No | System prompt (not inherited with previous_response_id) |
| `prompt` | object | No | Reusable prompt template with id, version, and variables |
| `previous_response_id` | string | No | ID of previous response for context continuation |
| `max_output_tokens` | integer | No | Maximum tokens to generate |
| `temperature` | float | No | Controls randomness (0.0-2.0) |
| `top_p` | float | No | Controls diversity via nucleus sampling |
| `stream` | boolean | No | Enable server-sent events streaming (default: false) |
| `background` | boolean | No | Enable background processing for long tasks |
| `store` | boolean | No | Enable 30-day storage (default: true) |

**Input Parameter Formats:**
- **String**: For simple prompts: `input="What is the weather?"`
- **Array**: For conversation history: `input=[{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi!"}]`
- When using `previous_response_id`, you typically use a string for the new user input

**Message Roles (in priority order):**
- **developer**: Highest priority, used for system-level instructions and business logic (use this instead of "system")
- **user**: End-user messages, prioritized behind developer messages
- **assistant**: Messages generated by the model
Note: The `instructions` parameter is equivalent to a developer message and takes highest priority

### Tool Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `tools` | array | List of available tools (both built-in and custom functions) |
| `tool_choice` | string/object | Control tool usage ("auto", "none", "required", or specific tool) |
| `parallel_tool_calls` | boolean | Allow parallel tool execution (default: true for all models) |

### Function Calling

The Responses API supports both built-in tools and custom function definitions. Custom functions allow you to extend the model's capabilities by defining your own tools.

#### Defining Custom Functions

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA"
                    },
                    "unit": {
                        "type": ["string", "null"],
                        "enum": ["celsius", "fahrenheit"],
                        "description": "The unit of temperature",
                        "default": null
                    }
                },
                "required": ["location", "unit"],
                "additionalProperties": false
            }
        }
    }
]
```

#### Tool Choice Options

- **"auto"**: Model decides whether to use tools
- **"none"**: Disable all tool usage
- **"required"**: Force the model to use at least one tool
- **Specific tool**: Force usage of a particular tool
  ```python
  tool_choice = {"type": "function", "function": {"name": "get_weather"}}
  ```

### Reusable Prompts

The Responses API supports reusable prompt templates that you can create and manage in the OpenAI dashboard. This allows you to iterate on prompts without changing your code.

```python
response = client.responses.create(
    model="gpt-4.1",
    prompt={
        "id": "pmpt_abc123",  # Prompt ID from dashboard
        "version": "2",       # Optional: specific version
        "variables": {        # Variables to substitute
            "customer_name": "Jane Doe",
            "product": "40oz juice box"
        }
    }
)
```

**Variables can include:**
- **String values**: Simple text substitutions
- **File inputs**: Reference uploaded files
  ```python
  "reference_pdf": {
      "type": "input_file",
      "file_id": file.id
  }
  ```
- **Image inputs**: Include images for analysis
- **Other message types**: Any valid input message type

### Reasoning Parameters

Reasoning models (o3, o3-pro, o4-mini) use internal reasoning tokens to "think" before generating responses. These parameters control the reasoning process:

| Parameter | Type | Description |
|-----------|------|-------------|
| `reasoning` | object | Control model reasoning behavior |
| `reasoning.effort` | string | "low", "medium", or "high" (default: "medium") |
| `reasoning.summary` | string | "auto", "none", "detailed", "concise", or custom prompt |
| `reasoning.encrypted_content` | string | Include in `include` array for stateless mode |

**Reasoning Effort Levels:**
- **low**: Favors speed and economical token usage
- **medium**: Balance between speed and reasoning accuracy (default)
- **high**: More complete reasoning for complex tasks

**Important Notes:**
- Reasoning tokens are billed as output tokens but not visible in the response
- Reasoning tokens are discarded after each turn (not retained in context)
- Reserve at least 25,000 tokens for reasoning when starting
- Use `max_output_tokens` to control total generation (reasoning + visible output)
- When using stateless mode (`store: false`), you must include `reasoning.encrypted_content` in the `include` array to preserve reasoning between API calls

### Additional Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `truncation` | string | Strategy for truncation (default: "disabled") |
| `text` | object | Control output format - use for Structured Outputs and JSON mode |
| `include` | array | Additional data to include in response |
| `metadata` | map | Custom metadata |
| `user` | string | Unique end-user identifier |
| `service_tier` | string | Specify service tier |

## Response Structure

### Standard Response Object

```python
{
    "id": "resp_abc123...",
    "object": "response",
    "created_at": 1234567890,
    "status": "completed",  # "queued", "in_progress", "completed", "incomplete", "cancelled", or "error"
    "model": "gpt-4o",
    "output": [
        {
            "id": "msg_123...",
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "The generated response text...",
                    "annotations": []
                }
            ]
        }
    ],
    "usage": {
        "input_tokens": 150,
        "output_tokens": 250,
        "total_tokens": 400
    }
}
```

**Note**: The response object does NOT include request parameters like temperature, tools, etc. For easy access to the text output, use `response.output_text` in the SDK.

### Response with Reasoning

```python
{
    "output": [
        {
            "type": "reasoning",
            "status": "completed",
            "content": [
                {
                    "type": "reasoning_text",
                    "text": "Internal reasoning process..."
                }
            ],
            "summary": "Concise summary of reasoning..."
        },
        {
            "type": "message",
            "status": "completed",
            "content": [
                {
                    "type": "output_text",
                    "text": "Final response to user..."
                }
            ]
        }
    ]
}
```

### Reasoning Items with Function Calls

When using reasoning models with function calling, you MUST preserve reasoning items between function calls:

```python
{
    "output": [
        {
            "type": "reasoning",
            "status": "completed",
            "content": [{"type": "reasoning_text", "text": "..."}],
            "encrypted_content": "..."  # For stateless mode
        },
        {
            "type": "function_call",
            "id": "fc_123",
            "call_id": "call_123",
            "name": "analyze_data",
            "arguments": "{\"data\": \"...\"}"
        }
    ],
    "usage": {
        "output_tokens": 1500,
        "output_tokens_details": {
            "reasoning_tokens": 1200  # Billed but not visible
        }
    }
}
```

**Critical**: When continuing after a function call, include ALL items (reasoning + function calls + outputs) since the last user message. This allows the model to maintain its reasoning chain.

### Response with Built-in Tool Calls

Each built-in tool has a specific response structure:

#### Web Search Response
```python
{
    "output": [
        {
            "type": "web_search_call",
            "id": "ws_abc123...",
            "status": "completed"
        },
        {
            "id": "msg_def456...",
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "Based on my search, here's what I found...",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "start_index": 123,
                            "end_index": 456,
                            "url": "https://example.com",
                            "title": "Example Article"
                        }
                    ]
                }
            ]
        }
    ]
}
```

#### File Search Response
```python
{
    "output": [
        {
            "type": "file_search_call",
            "id": "fs_abc123...",
            "status": "completed",
            "queries": ["What is deep research?"],
            "search_results": null  # Unless include=["file_search_call.results"]
        },
        {
            "id": "msg_def456...",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "According to the documents...",
                    "annotations": [
                        {
                            "type": "file_citation",
                            "index": 123,
                            "file_id": "file-abc123",
                            "filename": "document.pdf"
                        }
                    ]
                }
            ]
        }
    ]
}
```

#### Code Interpreter Response
```python
{
    "output": [
        {
            "type": "code_interpreter_call",
            "id": "ci_abc123...",
            "status": "completed",
            "container_id": "cntr_123..."
        },
        {
            "id": "msg_def456...",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "I've created a visualization for you...",
                    "annotations": [
                        {
                            "type": "container_file_citation",
                            "container_id": "cntr_123...",
                            "file_id": "cfile_456...",
                            "filename": "plot.png"
                        }
                    ]
                }
            ]
        }
    ]
}
```

#### Image Generation Response
```python
{
    "output": [
        {
            "type": "image_generation_call",
            "id": "ig_abc123...",
            "status": "completed",
            "result": "base64_encoded_image_data..."
        }
    ]
}
```

### Response with Custom Function Calls

```python
{
    "output": [
        {
            "type": "function_call",
            "id": "fc_xyz789",
            "call_id": "call_xyz789",
            "name": "get_weather",
            "arguments": "{\"location\": \"San Francisco, CA\", \"unit\": \"fahrenheit\"}"
        }
    ]
}
```

When the model calls a function, you need to execute it and provide the result back:

```python
# After receiving function call
tool_call = response.output[0]
args = json.loads(tool_call.arguments)

# Execute your function
result = get_weather(**args)  # Returns "72°F, sunny"

# Continue conversation with function result
input_messages.append(tool_call)  # Append the function call
input_messages.append({
    "type": "function_call_output",
    "call_id": tool_call.call_id,
    "output": str(result)
})

response = client.responses.create(
    model="gpt-4o",
    input=input_messages,
    tools=tools
)
```

## Vision and Image Input

The Responses API supports multimodal inputs, allowing models to analyze images alongside text. This enables powerful use cases like visual question answering, image description, and document analysis.

### Providing Images as Input

Images can be provided in three ways:

#### 1. URL Reference
```python
response = client.responses.create(
    model="gpt-4o",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {
                    "type": "input_image",
                    "image_url": "https://example.com/image.jpg"
                }
            ]
        }
    ]
)
```

#### 2. Base64 Encoding
```python
import base64

with open("image.jpg", "rb") as image_file:
    base64_image = base64.b64encode(image_file.read()).decode('utf-8')

response = client.responses.create(
    model="gpt-4o",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this image"},
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{base64_image}"
                }
            ]
        }
    ]
)
```

#### 3. File ID (for uploaded files)
```python
# First upload the image
file = client.files.create(
    file=open("image.jpg", "rb"),
    purpose="user_data"
)

# Then reference it
response = client.responses.create(
    model="gpt-4o",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What do you see?"},
                {
                    "type": "input_image",
                    "file_id": file.id
                }
            ]
        }
    ]
)
```

### Detail Parameter

Control the resolution and cost of image processing with the `detail` parameter:

```python
{
    "type": "input_image",
    "image_url": "https://example.com/image.jpg",
    "detail": "high"  # "low", "high", or "auto"
}
```

- **low**: Faster and cheaper, lower resolution (512x512)
- **high**: More detailed analysis, higher resolution
- **auto**: Model chooses based on image size (default)

### Supported Formats and Limits

- **Formats**: PNG, JPEG, WEBP, non-animated GIF
- **Size**: Maximum 20MB per image
- **Multiple images**: Can include multiple images in a single request

## Python SDK Implementation

### Basic Usage

```python
from openai import OpenAI

client = OpenAI()

# Simple text generation
response = client.responses.create(
    model="gpt-4o",
    input="Explain quantum computing in simple terms"
)

print(response.output_text)
```

### With Reasoning Models

```python
# Using o3 with high reasoning effort
response = client.responses.create(
    model="o3",
    input="Solve this complex mathematical problem: ...",
    reasoning={
        "effort": "high",
        "summary": "auto"
    }
)

# Access reasoning summary
if hasattr(response.output[0], 'summary'):
    print(f"Reasoning: {response.output[0].summary}")

# Access final output
for output in response.output:
    if output.type == "message":
        print(f"Answer: {output.content[0].text}")
```

### Stateful Conversations

#### Method 1: Manual State Management

```python
# Build conversation history manually
history = [
    {"role": "user", "content": "Tell me a joke"},
]

response = client.responses.create(
    model="gpt-4o",
    input=history,
    store=False  # Optional: disable storage
)

# Add response to history (only message items)
history.extend([
    {"role": el.role, "content": el.content} 
    for el in response.output
    if el.type == "message"  # Filter for message items only
])

# Continue conversation
history.append({"role": "user", "content": "Tell me another"})

response2 = client.responses.create(
    model="gpt-4o",
    input=history
)
```

#### Method 2: Automatic State Management (Recommended)

```python
# First message
response1 = client.responses.create(
    model="gpt-4o",
    input="Let's discuss machine learning concepts",
    store=True  # Default: responses stored for 30 days
)

# Continue conversation - automatically includes all context
response2 = client.responses.create(
    model="gpt-4o",
    input="Can you elaborate on neural networks?",
    previous_response_id=response1.id
)

# Chain multiple turns
response3 = client.responses.create(
    model="gpt-4.1",  # Can switch models mid-conversation
    input="How do transformers differ from CNNs?",
    previous_response_id=response2.id
)
```

### Streaming Responses

```python
# Enable streaming for real-time output
stream = client.responses.create(
    model="gpt-4o",
    input="Write a detailed story about space exploration",
    stream=True
)

for event in stream:
    if event.type == "ResponseOutputTextDelta":
        print(event.delta, end='', flush=True)
```

### Background Processing

Background mode enables reliable execution of long-running tasks (especially with o3/o3-pro) without timeouts:

```python
# Start background task
response = client.responses.create(
    model="o3-pro",
    input="Generate a comprehensive research report on climate change",
    reasoning={"effort": "high"},
    background=True,
    store=True  # Required for background mode
)

print(f"Task ID: {response.id}, Status: {response.status}")

# Poll for completion
import time
while response.status in ["queued", "in_progress"]:
    print(f"Status: {response.status}")
    time.sleep(5)  # Wait 5 seconds
    response = client.responses.retrieve(response.id)

print(f"Final status: {response.status}")
print(f"Output: {response.output_text}")

# Cancel if needed
# canceled_response = client.responses.cancel(response.id)
```

#### Background Streaming

```python
# Create and stream background response
stream = client.responses.create(
    model="o3",
    input="Write a detailed analysis...",
    background=True,
    stream=True  # Stream while processing in background
)

cursor = None
for event in stream:
    print(event)
    cursor = event.sequence_number

# If connection drops, resume from cursor
# (SDK support coming soon)
```

### Using Built-in Tools

```python
# Web search example with configuration
response = client.responses.create(
    model="gpt-4.1",  # Best for web search
    input="What are the latest developments in quantum computing as of 2024?",
    tools=[{
        "type": "web_search_preview",
        "search_context_size": "medium",  # low, medium, or high
        "user_location": {
            "type": "approximate",
            "country": "US",
            "city": "San Francisco",
            "region": "California"
        }
    }],
    tool_choice="auto"
)
print(response.output_text)

# Important: Web search citations
# When displaying web search results to users, citations MUST be:
# - Clearly visible in your UI
# - Clickable/interactive
# - Show both title and URL
# Note: Search tokens don't count against main model context

# File search example (requires vector store setup)
# First, create vector store and upload files
vector_store = client.vector_stores.create(name="my_knowledge_base")
file = client.files.create(file=open("document.pdf", "rb"), purpose="assistants")
client.vector_stores.files.create(vector_store_id=vector_store.id, file_id=file.id)

# Then use file search
response = client.responses.create(
    model="gpt-4o",
    input="Summarize the key findings from the uploaded research papers",
    tools=[{
        "type": "file_search",
        "vector_store_ids": [vector_store.id],
        "max_num_results": 5  # Optional: limit results
    }],
    tool_choice="auto"
)

# Code interpreter example (with container)
response = client.responses.create(
    model="gpt-4.1",
    input="Create a visualization of fibonacci sequence growth",
    tools=[{
        "type": "code_interpreter",
        "container": {"type": "auto"}  # Auto-creates container
    }],
    tool_choice="auto"
)

# Access generated files from code interpreter
for output in response.output:
    if output.type == "message":
        for annotation in output.content[0].annotations:
            if annotation.type == "container_file_citation":
                # Download the generated file
                file_content = client.containers.files.content(
                    container_id=annotation.container_id,
                    file_id=annotation.file_id
                )

# Image generation example with parameters
response = client.responses.create(
    model="gpt-4.1",
    input="Generate an image of a cat wearing a spacesuit",
    tools=[{
        "type": "image_generation",
        "size": "1024x1024",  # or "1024x1536", "auto"
        "quality": "high",    # "low", "medium", "high", "auto"
        "format": "png",      # output format
        "compression": 85,    # 0-100 for JPEG/WebP
        "background": "opaque"  # or "transparent", "auto"
    }]
)

# Extract base64 image
for output in response.output:
    if output.type == "image_generation_call":
        import base64
        image_data = base64.b64decode(output.result)
        with open("generated_image.png", "wb") as f:
            f.write(image_data)
```

## Structured Outputs

The Responses API supports Structured Outputs, ensuring model responses adhere to your specified JSON Schema. This provides reliable type-safety without needing to validate or retry incorrectly formatted responses.

### When to Use Structured Outputs

Use Structured Outputs via the `text` parameter when you want to structure the model's response to the user. Use function calling (with `strict: true`) when connecting the model to tools or external systems.

### Basic Structured Output Example

```python
from openai import OpenAI
from pydantic import BaseModel

client = OpenAI()

class CalendarEvent(BaseModel):
    name: str
    date: str
    participants: list[str]

response = client.responses.parse(
    model="gpt-4o-2024-08-06",
    input=[
        {"role": "developer", "content": "Extract the event information."},
        {"role": "user", "content": "Alice and Bob are going to a science fair on Friday."}
    ],
    text_format=CalendarEvent
)

event = response.output_parsed
print(event)  # CalendarEvent(name='science fair', date='Friday', participants=['Alice', 'Bob'])
```

### Using JSON Schema Directly

```python
response = client.responses.create(
    model="gpt-4o-2024-08-06",
    input=[
        {"role": "developer", "content": "You are a helpful math tutor."},
        {"role": "user", "content": "Solve 8x + 7 = -23"}
    ],
    text={
        "format": {
            "type": "json_schema",
            "name": "math_response",
            "schema": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "explanation": {"type": "string"},
                                "output": {"type": "string"}
                            },
                            "required": ["explanation", "output"],
                            "additionalProperties": False
                        }
                    },
                    "final_answer": {"type": "string"}
                },
                "required": ["steps", "final_answer"],
                "additionalProperties": False
            },
            "strict": True
        }
    }
)

print(response.output_text)
```

### Chain of Thought with Structured Outputs

```python
from pydantic import BaseModel

class Step(BaseModel):
    explanation: str
    output: str

class MathReasoning(BaseModel):
    steps: list[Step]
    final_answer: str

response = client.responses.parse(
    model="gpt-4o-2024-08-06",
    input=[
        {
            "role": "developer",
            "content": "You are a helpful math tutor. Guide through the solution step by step."
        },
        {"role": "user", "content": "How can I solve 8x + 7 = -23"}
    ],
    text_format=MathReasoning
)

math_reasoning = response.output_parsed
for i, step in enumerate(math_reasoning.steps):
    print(f"Step {i+1}: {step.explanation}")
    print(f"  => {step.output}")
print(f"Final Answer: {math_reasoning.final_answer}")
```

### Handling Refusals and Edge Cases

```python
try:
    response = client.responses.parse(
        model="gpt-4o-2024-08-06",
        input=[
            {"role": "developer", "content": "Extract user information."},
            {"role": "user", "content": "How do I hack into a system?"}
        ],
        text_format=UserInfo,
        max_output_tokens=50
    )
    
    # Check for refusals
    if response.output[0].content[0].type == "refusal":
        print(f"Model refused: {response.output[0].content[0].refusal}")
        return
    
    # Check for incomplete responses
    if response.status == "incomplete":
        if response.incomplete_details.reason == "max_output_tokens":
            print("Response truncated due to token limit")
        elif response.incomplete_details.reason == "content_filter":
            print("Response filtered for safety")
        return
    
    # Parse successful response
    user_info = response.output_parsed
    
except Exception as e:
    print(f"Error: {e}")
```

### Structured Outputs vs JSON Mode

| Feature | Structured Outputs | JSON Mode |
|---------|-------------------|-----------|
| Valid JSON | ✅ Yes | ✅ Yes |
| Schema adherence | ✅ Yes | ❌ No |
| Compatible models | gpt-4o-mini, gpt-4o-2024-08-06+ | All GPT-3.5+ models |
| Configuration | `text: { format: { type: "json_schema", ... } }` | `text: { format: { type: "json_object" } }` |

**Important for JSON Mode**: When using JSON mode, you MUST include the word "JSON" somewhere in the conversation (usually in the instructions or user message). The API will throw an error if "JSON" doesn't appear in the context.

### Schema Requirements and Limitations

1. **All fields must be required** (use union with `null` for optional fields)
2. **`additionalProperties: false`** must be set for all objects
3. **Root must be an object** (not `anyOf`, `oneOf`, or simple types)
4. **Supported types**: string, number, boolean, integer, object, array, enum, anyOf
5. **Max 100 object properties** with up to 5 levels of nesting
6. **Max 500 enum values** across all properties
7. **Unsupported keywords**: 
   - `allOf`, `not`, `oneOf` (except at root for refusals)
   - `minLength`, `maxLength`, `pattern` (for some models)
   - Most string validation keywords
8. **Key names**: Must not be `__proto__`, `prototype`, or `constructor`

### Using Custom Functions

```python
# Define custom function
def get_weather(location: str, unit: str = "fahrenheit") -> str:
    # Your implementation here
    return f"72°{unit[0].upper()}, sunny"

# Define function schema
weather_tool = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather in a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City and state, e.g. San Francisco, CA"
                },
                "unit": {
                    "type": ["string", "null"],
                    "enum": ["celsius", "fahrenheit"],
                    "default": null
                }
            },
            "required": ["location", "unit"],
            "additionalProperties": false
        }
    }
}

# Make request with custom function
response = client.responses.create(
    model="gpt-4.1",  # gpt-4.1 has excellent function calling capabilities
    input="What's the weather like in Tokyo?",
    tools=[weather_tool],
    tool_choice="auto"
)

# Handle function call
for tool_call in response.output:
    if tool_call.type == "function_call":
        # Parse arguments
        import json
        args = json.loads(tool_call.arguments)
        
        # Execute function
        if tool_call.name == "get_weather":
            result = get_weather(**args)
            
            # Continue conversation with result
            input_messages = [{"role": "user", "content": "What's the weather like in Tokyo?"}]
            input_messages.append(tool_call)  # Append function call
            input_messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": str(result)
            })
            
            follow_up = client.responses.create(
                model="gpt-4.1",
                input=input_messages,
                tools=[weather_tool]
            )
```

### Combining Built-in and Custom Tools

```python
# Mix built-in tools with custom functions
response = client.responses.create(
    model="gpt-4.1",
    input="Search for weather patterns in Tokyo and create a graph",
    tools=[
        {"type": "web_search_preview"},
        {"type": "code_interpreter", "container": {"type": "auto"}},
        weather_tool
    ],
    tool_choice="required",  # Force tool usage
    parallel_tool_calls=True
)
```

### Strict Mode for Function Calls

Enable strict mode to ensure function calls reliably adhere to the schema:

```python
weather_tool_strict = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather in a location",
        "strict": True,  # Enable strict mode
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City and state, e.g. San Francisco, CA"
                },
                "unit": {
                    "type": ["string", "null"],  # Optional field
                    "enum": ["celsius", "fahrenheit"]
                }
            },
            "required": ["location", "unit"],  # All fields must be listed
            "additionalProperties": False  # Required for strict mode
        }
    }
}
```

### Handling Multiple Function Calls

The model can call multiple functions in parallel:

```python
# Define email tool
email_tool = {
    "type": "function",
    "function": {
        "name": "send_email",
        "description": "Send an email to a recipient",
        "parameters": {
            "type": "object",
            "properties": {
                "recipient": {
                    "type": "string",
                    "description": "Email address of the recipient"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line"
                },
                "body": {
                    "type": "string",
                    "description": "Email body content"
                }
            },
            "required": ["recipient", "subject", "body"],
            "additionalProperties": false
        }
    }
}

# Response with multiple function calls
response = client.responses.create(
    model="gpt-4.1",
    input="What's the weather in Paris and Tokyo? Also send an email to Bob.",
    tools=[weather_tool, email_tool],
    parallel_tool_calls=True  # Default is True
)

# Build new input with original message and function calls/results
input_messages = [
    {"role": "user", "content": "What's the weather in Paris and Tokyo? Also send an email to Bob."}
]

# Process all function calls and add to input
for tool_call in response.output:
    if tool_call.type == "function_call":
        # Add the function call itself
        input_messages.append(tool_call)
        
        # Execute the function
        args = json.loads(tool_call.arguments)
        if tool_call.name == "get_weather":
            result = get_weather(**args)
        elif tool_call.name == "send_email":
            result = send_email(**args)
        
        # Add the function result
        input_messages.append({
            "type": "function_call_output",
            "call_id": tool_call.call_id,
            "output": str(result)
        })

# Send the complete conversation back
final_response = client.responses.create(
    model="gpt-4.1",
    input=input_messages,
    tools=[weather_tool, email_tool]
)
```

### Function Calling with Reasoning Models

When using reasoning models with function calls, you MUST preserve reasoning items:

```python
# Initial request with reasoning model
response = client.responses.create(
    model="o3",
    input="Analyze the weather patterns and determine the best travel day",
    tools=[weather_tool],
    reasoning={"effort": "high"}
)

# Collect ALL items since last user message
items_to_preserve = []
for item in response.output:
    items_to_preserve.append(item)
    
    if item.type == "function_call":
        # Execute function
        args = json.loads(item.arguments)
        result = get_weather(**args)
        
        # Add function result
        items_to_preserve.append({
            "type": "function_call_output",
            "call_id": item.call_id,
            "output": str(result)
        })

# Continue with ALL items (including reasoning)
final_response = client.responses.create(
    model="o3",
    input=[
        {"role": "user", "content": "Analyze the weather patterns..."},
        *items_to_preserve  # Includes reasoning + function calls + results
    ],
    tools=[weather_tool]
)
```

**Critical**: Always include reasoning items when continuing after function calls to maintain the model's chain of thought.

## Advanced Features

### 1. Combining Multiple Tools

```python
response = client.responses.create(
    model="gpt-4o",
    input="Research current AI trends and create a visualization",
    tools=[
        {"type": "web_search_preview"},
        {"type": "computer_use"}
    ],
    tool_choice="auto",
    parallel_tool_calls=True
)
```

### 2. Custom Instructions with Stateful Context

```python
response = client.responses.create(
    model="o3",
    input="Analyze this code for potential improvements",
    instructions="You are a senior software architect. Focus on performance and maintainability.",
    previous_response_id=previous_id,
    reasoning={"effort": "medium"}
)
```

### 3. Streaming with Background Processing

```python
stream = client.responses.create(
    model="o3",
    input="Generate comprehensive documentation for this codebase",
    background=True,
    stream=True,
    reasoning={"effort": "high"}
)

for event in stream:
    if event.type == "ResponseOutputTextDelta":
        print(event.delta, end='', flush=True)
    elif event.type == "response.reasoning_summary":
        print(f"\nReasoning: {event.summary}")
```

## Error Handling

### Error Types and Status Codes

```python
import openai
from openai import OpenAI

client = OpenAI()

try:
    response = client.responses.create(
        model="gpt-4o",
        input="Your prompt here"
    )
except openai.BadRequestError as e:
    print(f"Bad request (400): {e.message}")
except openai.AuthenticationError as e:
    print(f"Authentication failed (401): {e.message}")
except openai.PermissionDeniedError as e:
    print(f"Permission denied (403): {e.message}")
except openai.NotFoundError as e:
    print(f"Resource not found (404): {e.message}")
except openai.UnprocessableEntityError as e:
    print(f"Unprocessable entity (422): {e.message}")
except openai.RateLimitError as e:
    print(f"Rate limit exceeded (429): {e.message}")
    # Implement exponential backoff
except openai.InternalServerError as e:
    print(f"Server error (500+): {e.message}")
except openai.APIConnectionError as e:
    print(f"Connection error: {e.__cause__}")
except openai.APIStatusError as e:
    print(f"API error: Status {e.status_code}")
    print(f"Response: {e.response}")
```

### Handling Specific Response Errors

```python
response = client.responses.create(
    model="o3",
    input="Complex task",
    background=True
)

if response.status == "error":
    error_info = response.error
    print(f"Error type: {error_info.type}")
    print(f"Error message: {error_info.message}")
elif response.status == "incomplete":
    print("Response was incomplete, consider retrying")
```

## Best Practices

### 1. Model Selection Guidelines

```python
def select_model(task_type, context_size=None):
    """Select appropriate model based on task requirements"""
    
    if task_type == "quick_response":
        return "gpt-4o"  # ~200k context
    elif task_type == "large_context_analysis":
        return "gpt-4.1"  # ~1M context window
    elif task_type == "complex_reasoning":
        return "o3"  # Step-by-step reasoning
    elif task_type == "deep_analysis":
        return "o3-pro"  # Deep reasoning (10-30 min)
    elif task_type == "web_research":
        return "gpt-4.1"  # Best for web search with large context
    elif task_type == "codebase_navigation":
        return "gpt-4.1"  # Excellent for large file analysis
    elif context_size and context_size > 200000:
        return "gpt-4.1"  # Automatically use for large contexts
```

### 2. GPT-4.1 Specific Prompting Guide

GPT-4.1 is highly steerable and responsive to well-specified prompts. To get the most out of it:

#### System Prompt Reminders

Include these key reminders for agentic workflows:

```python
system_reminders = """
## PERSISTENCE
You are an agent - please keep going until the user's query is completely
resolved, before ending your turn and yielding back to the user. Only
terminate your turn when you are sure that the problem is solved.

## TOOL CALLING
If you are not sure about file content or codebase structure pertaining to
the user's request, use your tools to read files and gather the relevant
information: do NOT guess or make up an answer.

## PLANNING
You MUST plan extensively before each function call, and reflect
extensively on the outcomes of the previous function calls. DO NOT do this
entire process by making function calls only, as this can impair your
ability to solve the problem and think insightfully.
"""
```

#### Long Context Best Practices

For optimal performance with GPT-4.1's 1M token context:

1. **Use delimiters**: XML tags and structured formats work best
2. **Prompt organization**: Place critical instructions at both top AND bottom for best results
3. **Context placement**: Put the most relevant context near the user query

Example structure:
```python
prompt = f"""
<instructions>
{system_instructions}
</instructions>

<context>
{background_information}
</context>

<user_query>
{user_input}
</user_query>

<reminder>
Remember: {key_instructions}
</reminder>
"""
```

### 3. Prompt Caching

Structure your prompts to maximize caching benefits:

```python
# Place frequently reused content at the beginning
response = client.responses.create(
    model="gpt-4.1",
    instructions=standard_instructions,  # Reused across requests
    input=[
        {"role": "developer", "content": common_context},  # Cached
        {"role": "user", "content": unique_query}  # Variable part
    ]
)
```

**Benefits**:
- Reduced latency for repeated prompts
- Lower costs through cached token reuse
- Improved consistency across similar requests

### 4. Optimal Parameter Configuration

```python
# For deterministic outputs
deterministic_config = {
    "temperature": 0.0,
    "top_p": 1.0
}

# For creative tasks
creative_config = {
    "temperature": 0.8,
    "top_p": 0.9
}

# For reasoning tasks
reasoning_config = {
    "temperature": 0.2,
    "reasoning": {
        "effort": "high",
        "summary": "auto"
    }
}
```

### 3. Efficient Token Usage and Reasoning Management

```python
def optimize_for_reasoning(model, prompt, context_size):
    """Optimize token allocation for reasoning models"""
    
    # Reserve tokens for reasoning
    reasoning_buffer = {
        "o3": 25000,      # Complex reasoning
        "o3-pro": 50000,  # Deep reasoning (can be higher)
        "gpt-4o": 0,      # No reasoning tokens
        "gpt-4.1": 0      # No reasoning tokens
    }
    
    buffer = reasoning_buffer.get(model, 0)
    
    # Calculate available tokens for input/output
    available_tokens = context_size - buffer
    
    # Estimate input tokens
    input_tokens = len(prompt.split()) * 1.3
    
    if input_tokens > available_tokens * 0.8:
        # Use file_search or chunking approach
        return use_file_search_approach(prompt)
    
    return prompt, buffer

# Handle incomplete responses
def handle_reasoning_response(response):
    """Handle potential incomplete responses from reasoning models"""
    
    if response.status == "incomplete":
        reason = response.incomplete_details.reason
        
        if reason == "max_output_tokens":
            if response.output_text:
                print(f"Partial output: {response.output_text}")
            else:
                print("Ran out of tokens during reasoning phase")
                # Retry with higher max_output_tokens
                
        elif reason == "content_filter":
            print("Response filtered for safety")
    
    # Check reasoning token usage
    usage = response.usage
    if usage.output_tokens_details:
        reasoning_tokens = usage.output_tokens_details.reasoning_tokens
        print(f"Reasoning tokens used: {reasoning_tokens}")
```

### 4. Retry Logic with Exponential Backoff

```python
import time
from typing import Optional

def create_response_with_retry(
    client: OpenAI,
    max_retries: int = 3,
    **kwargs
) -> Optional[object]:
    """Create response with automatic retry on failure"""
    
    for attempt in range(max_retries):
        try:
            return client.responses.create(**kwargs)
        except openai.RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            wait_time = (2 ** attempt) + random.uniform(0, 1)
            print(f"Rate limited, waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
        except openai.APIError as e:
            if attempt == max_retries - 1:
                raise
            print(f"API error, retrying... ({attempt + 1}/{max_retries})")
            time.sleep(1)
    
    return None
```

## Complete Examples

### Example 1: Multi-Step Research Assistant

```python
from openai import OpenAI
import json

client = OpenAI()

class ResearchAssistant:
    def __init__(self, client):
        self.client = client
        self.conversation_id = None
    
    def research_topic(self, topic):
        """Conduct comprehensive research on a topic"""
        
        # Step 1: Initial web search with gpt-4.1 for comprehensive results
        print("🔍 Searching for information...")
        search_response = self.client.responses.create(
            model="gpt-4.1",  # Best for web search with large context
            input=f"Search for comprehensive information about: {topic}",
            tools=[{"type": "web_search_preview"}],
            tool_choice="auto"
        )
        self.conversation_id = search_response.id
        
        # Step 2: Deep analysis with reasoning
        print("🧠 Analyzing findings...")
        analysis_response = self.client.responses.create(
            model="o3",
            input="Analyze the search results and provide key insights",
            previous_response_id=self.conversation_id,
            reasoning={
                "effort": "high",
                "summary": "auto"
            }
        )
        
        # Step 3: Create visualization
        print("📊 Creating visualization...")
        viz_response = self.client.responses.create(
            model="gpt-4o",
            input="Create a visualization summarizing the key findings",
            previous_response_id=analysis_response.id,
            tools=[{"type": "computer_use"}],
            tool_choice="auto"
        )
        
        return {
            "search_results": search_response,
            "analysis": analysis_response,
            "visualization": viz_response
        }

# Usage
assistant = ResearchAssistant(client)
results = assistant.research_topic("quantum computing applications in medicine")
```

### Example 2: Code Analysis with File Processing

```python
class CodeAnalyzer:
    def __init__(self, client):
        self.client = client
    
    def analyze_codebase(self, file_paths):
        """Analyze multiple code files for improvements"""
        
        # Upload files for analysis
        file_contents = []
        for path in file_paths:
            with open(path, 'r') as f:
                file_contents.append({
                    "name": path,
                    "content": f.read()
                })
        
        # Perform analysis with o3
        response = self.client.responses.create(
            model="o3",
            input=f"""Analyze these code files for:
            1. Performance bottlenecks
            2. Security vulnerabilities
            3. Code quality issues
            4. Suggested improvements
            
            Files: {json.dumps([f['name'] for f in file_contents])}
            """,
            instructions="You are a senior software architect with expertise in code review.",
            reasoning={
                "effort": "high",
                "summary": "Provide a concise summary of major findings"
            },
            max_output_tokens=4000
        )
        
        return response

# Usage
analyzer = CodeAnalyzer(client)
analysis = analyzer.analyze_codebase([
    "src/main.py",
    "src/utils.py",
    "src/database.py"
])
```

### Example 3: Large-Scale Analysis with GPT-4.1

```python
class LargeScaleAnalyzer:
    """Demonstrates gpt-4.1's 1M token context window and advanced function calling"""
    
    def __init__(self, client):
        self.client = client
        self.session_id = None
        
        # Define multiple analysis functions
        self.analysis_tools = [
            {
                "type": "function",
                "name": "analyze_codebase",
                "description": "Analyze code structure and dependencies",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "analysis_type": {
                            "type": "string",
                            "enum": ["architecture", "dependencies", "security", "performance"]
                        },
                        "files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1
                        },
                        "depth": {
                            "type": "string",
                            "enum": ["shallow", "deep"],
                            "description": "Level of analysis depth"
                        }
                    },
                    "required": ["analysis_type", "files", "depth"],
                    "additionalProperties": False
                }
            },
            {
                "type": "function", 
                "name": "search_patterns",
                "description": "Search for specific patterns across files",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Regex patterns to search"
                        },
                        "file_extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "File types to search"
                        }
                    },
                    "required": ["patterns", "file_extensions"],
                    "additionalProperties": False
                }
            },
            {"type": "web_search_preview"},  # Built-in tool
            {"type": "file_search_preview"}   # Built-in tool
        ]
    
    def analyze_large_codebase(self, directory_path, context_files):
        """Analyze entire codebase with gpt-4.1's large context"""
        
        # Load massive context (up to 1M tokens)
        all_files = []
        for file_path in context_files:
            with open(file_path, 'r') as f:
                all_files.append({
                    "path": file_path,
                    "content": f.read()
                })
        
        # Initial analysis with multiple function calls
        response = self.client.responses.create(
            model="gpt-4.1",  # 1M token context window
            input=[{
                "role": "developer",
                "content": "You are an expert code analyzer. Use available tools to thoroughly analyze the codebase."
            }, {
                "role": "user",
                "content": f"""Analyze this large codebase:
                Directory: {directory_path}
                Total files: {len(all_files)}
                
                Perform:
                1. Architecture analysis
                2. Security vulnerability scan
                3. Search for deprecated patterns
                4. Find performance bottlenecks
                5. Search web for best practices for similar projects
                
                Context: {json.dumps(all_files[:100])}  # First 100 files
                """
            }],
            tools=self.analysis_tools,
            tool_choice="required",  # Force tool usage
            parallel_tool_calls=True,  # Allow multiple parallel calls
            max_output_tokens=8000
        )
        
        self.session_id = response.id
        
        # Process function calls
        results = self._process_function_calls(response)
        
        # Continue analysis with results
        return self._synthesize_results(results)
    
    def _process_function_calls(self, response):
        """Execute all function calls from response"""
        results = []
        input_messages = []
        
        for output in response.output:
            if output.type == "function_call":
                # Execute based on function name
                result = self._execute_function(output)
                results.append(result)
                
                # Prepare for follow-up
                input_messages.append(output)
                input_messages.append({
                    "type": "function_call_output",
                    "call_id": output.call_id,
                    "output": json.dumps(result)
                })
        
        return {"calls": response.output, "results": results, "messages": input_messages}
    
    def _execute_function(self, call):
        """Execute individual function call"""
        args = json.loads(call.arguments)
        
        if call.name == "analyze_codebase":
            # Simulate codebase analysis
            return {
                "analysis_type": args["analysis_type"],
                "findings": f"Found issues in {len(args['files'])} files",
                "severity": "medium" if args["depth"] == "shallow" else "high"
            }
        elif call.name == "search_patterns":
            # Simulate pattern search
            return {
                "patterns_found": len(args["patterns"]),
                "files_matched": 42,
                "examples": ["Example match 1", "Example match 2"]
            }
        
        return {"status": "completed"}
    
    def _synthesize_results(self, results):
        """Synthesize all results into final report"""
        response = self.client.responses.create(
            model="gpt-4.1",
            input=results["messages"],
            previous_response_id=self.session_id,
            tools=self.analysis_tools,
            instructions="Synthesize all findings into a comprehensive report with actionable recommendations."
        )
        
        return response

# Usage
analyzer = LargeScaleAnalyzer(client)
report = analyzer.analyze_large_codebase(
    "/path/to/project",
    ["file1.py", "file2.py", ...]  # Can handle thousands of files
)
```

### Example 4: Interactive Tutoring System

```python
class InteractiveTutor:
    def __init__(self, client):
        self.client = client
        self.session_id = None
        
    def start_lesson(self, topic):
        """Start an interactive lesson"""
        response = self.client.responses.create(
            model="gpt-4o",
            input=f"Let's start a lesson on {topic}. Begin with an overview.",
            instructions="You are an expert tutor. Be encouraging and adaptive."
        )
        self.session_id = response.id
        return response
    
    def ask_question(self, question):
        """Continue the lesson with a question"""
        response = self.client.responses.create(
            model="gpt-4o",
            input=question,
            previous_response_id=self.session_id,
            stream=True
        )
        
        full_response = ""
        for event in response:
            if event.type == "ResponseOutputTextDelta":
                print(event.delta, end='', flush=True)
                full_response += event.delta
        
        return full_response
    
    def generate_exercise(self):
        """Generate an exercise based on the lesson"""
        return self.client.responses.create(
            model="gpt-4o",
            input="Generate a practical exercise based on what we've discussed",
            previous_response_id=self.session_id,
            tools=[{"type": "code_interpreter", "container": {"type": "auto"}}],  # Can create code examples
            tool_choice="auto"
        )

# Usage
tutor = InteractiveTutor(client)
lesson = tutor.start_lesson("Python decorators")
print(lesson.output_text)

# Interactive Q&A
response = tutor.ask_question("How do decorators handle function arguments?")

# Generate exercise
exercise = tutor.generate_exercise()
```

## Migration from Chat Completions API

If you're migrating from the Chat Completions API, here are the key differences:

### Old Way (Chat Completions)
```python
# Chat Completions API
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "developer", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]
)
print(response.choices[0].message.content)
```

### New Way (Responses API)
```python
# Responses API
response = client.responses.create(
    model="gpt-4o",
    instructions="You are a helpful assistant.",
    input="Hello!"
)
print(response.output_text)
```

### Key Migration Points:
1. `messages` → `input` (can be string or array)
2. `system` message → `instructions` parameter
3. `response.choices[0].message.content` → `response.output_text`
4. Built-in tools available without function calling setup
5. Stateful conversations via `previous_response_id`
6. Native support for reasoning models (o3, o3-pro)

## Important Limitations and Requirements

### Tool-Specific Limitations

#### Web Search
- Not supported in `gpt-4.1-nano` model
- Limited to 128,000 token context window (even with gpt-4.1)
- Search context tokens are separate from main model context and not carried between turns
- Citations must be clearly visible and clickable in your UI

#### File Search
- Requires prior setup of vector stores
- Files must be uploaded to vector stores before use
- Limited file format support (see documentation for full list)

#### Code Interpreter
- Containers expire after 20 minutes of inactivity
- All container data is ephemeral - download important files immediately
- Container state cannot be restored after expiration

#### Background Mode
- Requires `store=true` (stateless requests rejected)
- Higher time-to-first-token compared to synchronous responses
- Must poll for completion or use streaming

### Model-Specific Limitations

- **gpt-4.1-nano**: No web search support, may call same tool multiple times with `parallel_tool_calls`
- **Reasoning models**: Reasoning tokens discarded after each turn (not retained in context)

### Cost Implications
- When using `previous_response_id`, all previous input tokens in the chain are billed as input tokens
- Reasoning tokens are billed as output tokens but not visible in the response
- Web search pricing varies by `search_context_size` parameter

## Conclusion

The OpenAI Responses API represents a significant evolution in AI API design, unifying multiple capabilities into a single, powerful interface. By understanding its features and implementing the patterns shown in this guide, you can build sophisticated AI applications that leverage state-of-the-art language models with advanced reasoning capabilities, tool integration, and efficient conversation management.

Key takeaways:
- **Model Selection**: Use gpt-4.1 for large context (1M tokens) and web search, o3/o3-pro for reasoning tasks
- **Function Calling**: Supports both custom functions and built-in tools with parallel execution
- **Structured Outputs**: Ensure type-safe responses with JSON Schema validation
- **Stateful Conversations**: Maintain context across interactions with `previous_response_id`
- **Error Handling**: Properly handle refusals, incomplete responses, and edge cases
- **Streaming**: Process responses in real-time for better user experience

Remember to:
- Choose the right model for your use case (gpt-4.1 for large contexts, o3 for reasoning)
- Pin to specific model snapshots in production (e.g., gpt-4.1-2025-04-14)
- Leverage built-in tools (web_search_preview, file_search, code_interpreter, image_generation, computer_use, mcp)
- Use strict mode for reliable function calling
- Implement Structured Outputs for type-safe responses
- Take advantage of parallel tool calls for efficiency
- Monitor token usage and costs, especially with large contexts
- Set up vector stores before using file_search
- Configure containers for code_interpreter
- Ensure web search citations are visible and clickable
- Only use trusted MCP servers due to security risks
- Use `developer` role instead of `system` for high-priority instructions
- Structure prompts for caching by placing reusable content at the beginning

With these tools and knowledge, you're ready to build the next generation of AI-powered applications using the OpenAI Responses API.
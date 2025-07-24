"""Tool definitions for all supported models."""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from .base import ToolSpec
from .descriptors import Route
from .registry import tool

# Import tools to ensure registration
from . import search_history  # noqa: F401
# Note: search_attachments is not imported here to prevent MCP exposure
# It remains available for internal model function calling
# Note: logging_tools is imported conditionally in integration.py when developer mode is enabled


@tool
class ChatWithGemini25Pro(ToolSpec):
    """Deep multimodal analysis and complex reasoning (Gemini 2.5 Pro, ~1M context).
    Excels at: bug fixing, code analysis, multimodal understanding.

    Example usage:
    - instructions: "Analyze this codebase architecture and identify potential performance bottlenecks"
    - output_format: "Provide a structured analysis with: 1) Architecture overview 2) Identified bottlenecks 3) Recommendations"
    - context: ["/project/src", "/project/tests"]
    - temperature: 1.0 (default, neutral for Gemini)
    - reasoning_effort: "medium" (default, increase to "high" for complex analysis)"""

    model_name = "gemini-2.5-pro"
    adapter_class = "vertex"
    context_window = 1_000_000
    timeout = 600

    # Custom prompt template for Gemini models
    prompt_template = """<task_instructions>
{instructions}
</task_instructions>

<expected_output_format>
{output_format}
</expected_output_format>

<context_information>
{context}
</context_information>"""

    # Parameters
    # Required parameters first
    instructions: str = Route.prompt(
        pos=0, description="Task instructions for the model"
    )
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(
        pos=2,
        description="List of file/directory paths to include (e.g., ['/path/to/file.py', '/path/to/dir'])",
    )
    session_id: str = Route.session(
        description="Session ID for multi-turn conversations"
    )
    # Optional parameters
    priority_context: Optional[List[str]] = Route.prompt(
        description="Files/directories to prioritize for inline inclusion"
    )
    structured_output_schema: Optional[str] = Route.structured_output(
        description="JSON schema for structured output validation. For OpenAI models: requires strict validation with 'additionalProperties: false' at every object level and all properties with constraints (minimum, maximum, enum, pattern) must be listed in 'required'"
    )
    temperature: Optional[float] = Route.adapter(
        default=1.0, description="Sampling temperature (0.0-2.0 for Gemini)"
    )
    reasoning_effort: Optional[str] = Route.adapter(
        default="medium",
        description="Controls reasoning effort (low/medium/high) - maps to thinking_budget internally",
    )
    disable_memory_search: Optional[bool] = Route.adapter(
        default=False,
        description="Disable search_project_history tool to prevent access to past conversations",
    )


@tool
class ChatWithGemini25Flash(ToolSpec):
    """Fast summarization and quick analysis (Gemini 2.5 Flash, ~1M context).
    Excels at: rapid insights, triage, quick summaries.

    Example usage:
    - instructions: "Summarize the recent changes in this project and highlight any breaking changes"
    - output_format: "Bullet points with: • Summary of changes • Breaking changes (if any) • Migration notes"
    - context: ["/project/CHANGELOG.md", "/project/src/api"]
    - temperature: 0.3 (default, balanced for summaries)"""

    model_name = "gemini-2.5-flash"
    adapter_class = "vertex"
    context_window = 1_000_000
    timeout = 300

    # Parameters
    # Required parameters first
    instructions: str = Route.prompt(
        pos=0, description="Task instructions for the model"
    )
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(
        pos=2,
        description="List of file/directory paths to include (e.g., ['/path/to/file.py', '/path/to/dir'])",
    )
    session_id: str = Route.session(
        description="Session ID for multi-turn conversations"
    )
    # Optional parameters
    priority_context: Optional[List[str]] = Route.prompt(
        description="Files/directories to prioritize for inline inclusion"
    )
    structured_output_schema: Optional[str] = Route.structured_output(
        description="JSON schema for structured output validation. For OpenAI models: requires strict validation with 'additionalProperties: false' at every object level and all properties with constraints (minimum, maximum, enum, pattern) must be listed in 'required'"
    )
    temperature: Optional[float] = Route.adapter(
        default=1.0, description="Sampling temperature (0.0-2.0 for Gemini)"
    )
    reasoning_effort: Optional[str] = Route.adapter(
        default="low",
        description="Controls reasoning effort (low/medium/high) - maps to thinking_budget internally",
    )
    disable_memory_search: Optional[bool] = Route.adapter(
        default=False,
        description="Disable search_project_history tool to prevent access to past conversations",
    )


@tool
class ChatWithO3(ToolSpec):
    """Chain-of-thought reasoning and algorithm design (OpenAI o3, ~200k context).
    Excels at: step-by-step problem solving, algorithm design, code generation.

    Example usage:
    - instructions: "Design an efficient algorithm to find all cycles in a directed graph"
    - output_format: "Show: 1) Algorithm approach 2) Step-by-step implementation 3) Time/space complexity"
    - context: ["/project/src/graph.py"]
    - reasoning_effort: "medium" (default, increase to "high" for complex problems)
    - session_id: "graph-algo-001" (for multi-turn refinement)"""

    model_name = "o3"
    adapter_class = "openai"
    context_window = 200_000
    timeout = 1800

    # Custom prompt template for o3 reasoning models
    prompt_template = """## Task Instructions
{instructions}

## Output Requirements
{output_format}

## Provided Context
{context}

Please approach this task step-by-step, showing your reasoning process."""

    # Parameters
    # Required parameters first
    instructions: str = Route.prompt(
        pos=0, description="Task instructions for the model"
    )
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(
        pos=2,
        description="List of file/directory paths to include (e.g., ['/path/to/file.py', '/path/to/dir'])",
    )
    session_id: str = Route.session(
        description="Session ID for multi-turn conversations"
    )
    # Optional parameters with defaults
    priority_context: Optional[List[str]] = Route.prompt(
        description="Files/directories to prioritize for inline inclusion"
    )
    structured_output_schema: Optional[str] = Route.structured_output(
        description="JSON schema for structured output validation. For OpenAI models: requires strict validation with 'additionalProperties: false' at every object level and all properties with constraints (minimum, maximum, enum, pattern) must be listed in 'required'"
    )
    reasoning_effort: Optional[str] = Route.adapter(
        default="medium", description="Controls reasoning effort (low/medium/high)"
    )
    disable_memory_search: Optional[bool] = Route.adapter(
        default=False,
        description="Disable search_project_history tool to prevent access to past conversations",
    )


@tool
class ChatWithO3Pro(ToolSpec):
    """Deep analysis and formal reasoning (OpenAI o3-pro, ~200k context).
    Excels at: formal proofs, complex debugging, architectural analysis.
    Note: Can take 10-30 minutes for deep reasoning.

    Example usage:
    - instructions: "Prove the correctness of this distributed consensus algorithm and identify edge cases"
    - output_format: "Formal analysis with: 1) Correctness proof 2) Safety/liveness properties 3) Edge cases"
    - context: ["/project/src/consensus", "/project/docs/algorithm.md"]
    - reasoning_effort: "high" (default, for thorough analysis)
    - max_reasoning_tokens: 100000 (optional, for complex proofs)
    - session_id: "consensus-proof-001"""

    model_name = "o3-pro"
    adapter_class = "openai"
    context_window = 200_000
    timeout = 2700  # 45 minutes

    # Parameters
    # Required parameters first
    instructions: str = Route.prompt(
        pos=0, description="Task instructions for the model"
    )
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(
        pos=2,
        description="List of file/directory paths to include (e.g., ['/path/to/file.py', '/path/to/dir'])",
    )
    session_id: str = Route.session(
        description="Session ID for multi-turn conversations"
    )
    # Optional parameters with defaults
    priority_context: Optional[List[str]] = Route.prompt(
        description="Files/directories to prioritize for inline inclusion"
    )
    max_reasoning_tokens: Optional[int] = Route.adapter(
        default=None, description="Maximum reasoning tokens"
    )
    structured_output_schema: Optional[str] = Route.structured_output(  # type: ignore[misc]
        description="JSON schema for structured output validation. For OpenAI models: requires strict validation with 'additionalProperties: false' at every object level and all properties with constraints (minimum, maximum, enum, pattern) must be listed in 'required'"
    )
    reasoning_effort: Optional[str] = Route.adapter(
        default="high", description="Controls reasoning effort (low/medium/high)"
    )
    disable_memory_search: Optional[bool] = Route.adapter(
        default=False,
        description="Disable search_project_history tool to prevent access to past conversations",
    )


@tool
class ChatWithGPT4_1(ToolSpec):
    """Fast long-context processing with web search (GPT-4.1, ~1M context).
    Excels at: large-scale refactoring, codebase navigation, RAG workflows, current information retrieval.

    Example usage:
    - instructions: "Refactor this codebase to use modern React patterns and hooks"
    - output_format: "Migration guide with: 1) Files to change 2) Specific refactoring steps 3) Testing checklist"
    - context: ["/project/src/components"]
    - priority_context: ["/project/legacy"] (optional, prioritize these files inline)
    - temperature: 0.2 (default, for consistent refactoring)
    - session_id: "react-refactor-001"""

    model_name = "gpt-4.1"
    adapter_class = "openai"
    context_window = 1_000_000
    timeout = 300

    # Parameters
    # Required parameters first
    instructions: str = Route.prompt(
        pos=0, description="Task instructions for the model"
    )
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(
        pos=2,
        description="List of file/directory paths to include (e.g., ['/path/to/file.py', '/path/to/dir'])",
    )
    session_id: str = Route.session(
        description="Session ID for multi-turn conversations"
    )
    # Optional parameters with defaults
    priority_context: Optional[List[str]] = Route.prompt(
        description="Files/directories to prioritize for inline inclusion"
    )
    structured_output_schema: Optional[str] = Route.structured_output(
        description="JSON schema for structured output validation. For OpenAI models: requires strict validation with 'additionalProperties: false' at every object level and all properties with constraints (minimum, maximum, enum, pattern) must be listed in 'required'"
    )
    temperature: Optional[float] = Route.adapter(
        default=0.2, description="Sampling temperature"
    )
    disable_memory_search: Optional[bool] = Route.adapter(
        default=False,
        description="Disable search_project_history tool to prevent access to past conversations",
    )


@tool
class ResearchWithO3DeepResearch(ToolSpec):
    """Ultra-deep research with autonomous web search and reasoning (OpenAI o3-deep-research, ~200k context).
    Excels at: comprehensive research, deep analysis with real-time information, complex investigations.
    WARNING: This is a research tool that can take 10-60 minutes to complete. The model performs
    extensive web searches and deep reasoning. Use for tasks requiring thorough investigation.

    Example usage:
    - instructions: "Research the latest advances in quantum error correction codes and their practical implementations"
    - output_format: "Comprehensive report with: 1) Current state of the field 2) Recent breakthroughs 3) Implementation challenges 4) Future directions"
    - context: [] (empty for pure web research, or include papers/code for analysis)
    - session_id: "quantum-research-001" (for follow-up questions)"""

    model_name = "o3-deep-research"
    adapter_class = "openai"
    context_window = 200_000
    timeout = 3600  # 1 hour

    # Use the same prompt template as o3
    prompt_template = """## Task Instructions
{instructions}

## Output Requirements
{output_format}

## Provided Context
{context}

Please approach this task step-by-step, showing your reasoning process."""

    # Parameters
    # Required parameters first
    instructions: str = Route.prompt(
        pos=0, description="Task instructions for the model"
    )
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(
        pos=2,
        description="List of file/directory paths to include (e.g., ['/path/to/file.py', '/path/to/dir'])",
    )
    session_id: str = Route.session(
        description="Session ID for multi-turn conversations"
    )
    # Optional parameters with defaults
    priority_context: Optional[List[str]] = Route.prompt(
        description="Files/directories to prioritize for inline inclusion"
    )


@tool
class ResearchWithO4MiniDeepResearch(ToolSpec):
    """Fast research with autonomous web search (OpenAI o4-mini-deep-research, ~200k context).
    Excels at: quick research tasks, cost-efficient analysis with web search, rapid information gathering.
    WARNING: This is a research tool that typically takes 2-10 minutes to complete. The model performs
    web searches and analysis autonomously. More cost-efficient than o3-deep-research.

    Example usage:
    - instructions: "Research current best practices for API versioning and backwards compatibility"
    - output_format: "Summary with: 1) Common approaches 2) Pros/cons 3) Industry examples 4) Recommendations"
    - context: ["/project/api/v1"] (optional, to analyze current implementation)
    - session_id: "api-research-001"""

    model_name = "o4-mini-deep-research"
    adapter_class = "openai"
    context_window = 200_000
    timeout = 900  # 15 minutes

    # Parameters
    # Required parameters first
    instructions: str = Route.prompt(
        pos=0, description="Task instructions for the model"
    )
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(
        pos=2,
        description="List of file/directory paths to include (e.g., ['/path/to/file.py', '/path/to/dir'])",
    )
    session_id: str = Route.session(
        description="Session ID for multi-turn conversations"
    )
    # Optional parameters with defaults
    priority_context: Optional[List[str]] = Route.prompt(
        description="Files/directories to prioritize for inline inclusion"
    )


# # Disabled - Gemini and OpenAI models provide better alternatives
# # @tool
# # class ChatWithGrok3(ToolSpec):
#     """General-purpose assistant using xAI Grok 3 Fast model (131k context).
#     Excels at: coding, Q&A, and real-time info via X data.
#
#     Example usage:
#     - instructions: "Summarize the latest AI news from X"
#     - output_format: "Bullet points with links"
#     - context: ["/project/docs/requirements.md"]
#     - temperature: 0.3 (lower for consistency)
#     - session_id: "grok-session-001" (for conversations)
#     """
#
#     model_name = "grok-3-fast"
#     adapter_class = "xai"
#     context_window = 131_000
#     timeout = 300
#
#     # Required parameters
#     instructions: str = Route.prompt(pos=0, description="User instructions or question")
#     output_format: str = Route.prompt(
#         pos=1, description="Desired output format or response style"
#     )
#     context: List[str] = Route.prompt(
#         pos=2, description="File paths or content to provide as context"
#     )
#     session_id: str = Route.session(
#         description="Session ID to link multi-turn conversations"
#     )
#
#     # Optional parameters
#     attachments: Optional[List[str]] = Route.vector_store(
#         description="Additional files for RAG"
#     )
#     structured_output_schema: Optional[str] = Route.structured_output(
#         description="JSON Schema for structured output (optional)"
#     )
#     temperature: Optional[float] = Route.adapter(
#         default=1.0, description="Sampling temperature (0-2)"
#     )
#


@tool
class ChatWithGrok4(ToolSpec):
    """Advanced assistant using xAI Grok 4 model (256k context, multi-agent reasoning).
    Excels at: complex reasoning, code analysis, large documents.

    Example usage:
    - instructions: "Analyze this entire codebase and suggest refactoring"
    - output_format: "Detailed report with code examples"
    - context: ["/src"] (can handle massive contexts)
    - session_id: "grok4-analysis-001"

    Live Search examples:
    - search_mode: "on" + instructions: "What are the latest AI developments in 2025?"
    - search_mode: "auto" (default, searches only when needed)
    - search_mode: "off" (no web search, uses training data only)
    - search_parameters: {"allowedWebsites": ["arxiv.org"], "maxSearchResults": 10}
    """

    model_name = "grok-4"
    adapter_class = "xai"
    context_window = 256_000
    timeout = 600  # Longer timeout for complex reasoning

    # Required parameters
    instructions: str = Route.prompt(pos=0, description="User instructions")
    output_format: str = Route.prompt(
        pos=1, description="Format requirements for the answer"
    )
    context: List[str] = Route.prompt(
        pos=2, description="Context file paths or snippets"
    )
    session_id: str = Route.session(description="Session ID for multi-turn context")

    # Optional parameters
    priority_context: Optional[List[str]] = Route.prompt(
        description="Files/directories to prioritize for inline inclusion"
    )
    structured_output_schema: Optional[str] = Route.structured_output(
        description="JSON Schema for structured output (optional)"
    )
    search_parameters: Optional[Dict[str, Any]] = Route.adapter(
        description="Advanced Live Search settings: allowedWebsites, excludedWebsites, maxSearchResults (1-20), safeSearch, fromDate, toDate, xHandles"
    )
    temperature: Optional[float] = Route.adapter(
        default=0.7, description="Sampling temperature (0-2)"
    )
    search_mode: Optional[str] = Route.adapter(
        default="auto",
        description="Live Search mode: 'auto' (searches when needed), 'on' (always search), 'off' (no search)",
    )
    return_citations: Optional[bool] = Route.adapter(
        default=True,
        description="Include source URLs and titles when Live Search is used",
    )
    disable_memory_search: Optional[bool] = Route.adapter(
        default=False,
        description="Disable search_project_history tool to force use of attachments",
    )


@tool
class ChatWithGrok3Reasoning(ToolSpec):
    """Deep reasoning using xAI Grok 3 Beta model (131k context).
    Excels at: complex problem solving, mathematical reasoning, code debugging.
    Note: General purpose Grok 3 model.

    Example usage:
    - instructions: "Find and fix the race condition in this concurrent code"
    - output_format: "Step-by-step analysis with fixed code"
    - context: ["/src/concurrency/"]
    - session_id: "debug-session-001"

    Live Search examples:
    - search_mode: "on" + instructions: "What's the latest research on quantum algorithms?"
    - search_mode: "auto" (default, searches when current info needed)
    - search_mode: "off" (pure reasoning without web search)
    - search_parameters: {"excludedWebsites": ["reddit.com"], "safeSearch": "strict"}
    """

    model_name = "grok-3-beta"
    adapter_class = "xai"
    context_window = 131_000
    timeout = 900  # Longer timeout for reasoning mode

    # Required parameters
    instructions: str = Route.prompt(pos=0, description="Complex problem or question")
    output_format: str = Route.prompt(pos=1, description="Desired output structure")
    context: List[str] = Route.prompt(pos=2, description="Relevant context files")
    session_id: str = Route.session(description="Session ID for multi-step reasoning")

    # Optional parameters
    priority_context: Optional[List[str]] = Route.prompt(
        description="Files/directories to prioritize for inline inclusion"
    )
    structured_output_schema: Optional[str] = Route.structured_output(
        description="JSON Schema for structured output (optional)"
    )
    search_parameters: Optional[Dict[str, Any]] = Route.adapter(
        description="Advanced Live Search settings: allowedWebsites, excludedWebsites, maxSearchResults (1-20), safeSearch, fromDate, toDate, xHandles"
    )
    temperature: Optional[float] = Route.adapter(
        default=0.3, description="Lower temp for consistent reasoning"
    )
    search_mode: Optional[str] = Route.adapter(
        default="auto",
        description="Live Search mode: 'auto' (searches when needed), 'on' (always search), 'off' (no search)",
    )
    return_citations: Optional[bool] = Route.adapter(
        default=True,
        description="Include source URLs and titles when Live Search is used",
    )
    disable_memory_search: Optional[bool] = Route.adapter(
        default=False,
        description="Disable search_project_history tool to force use of attachments",
    )


# @tool
# class ChatWithGrok3Mini(ToolSpec):
#     """Quick responses with xAI Grok 3 Mini model (32k context).
#     Excels at: rapid insights, cost-effective reasoning tasks.
#     Supports reasoning_effort parameter for adjustable processing depth.
#
#     Example usage:
#     - instructions: "Summarize this log file and identify critical errors"
#     - output_format: "Bullet points with error summaries"
#     - context: ["/var/log/app.log"]
#     - reasoning_effort: "low" (default, can be "medium" or "high")
#     - session_id: "log-analysis-001"
#     """
#
#     model_name = "grok-3-mini"
#     adapter_class = "xai"
#     context_window = 32_000
#     timeout = 120
#
#     # Required parameters
#     instructions: str = Route.prompt(pos=0, description="User instructions or question")
#     output_format: str = Route.prompt(
#         pos=1, description="Desired output format or response style"
#     )
#     context: List[str] = Route.prompt(
#         pos=2, description="File paths or content to provide as context"
#     )
#     session_id: str = Route.session(
#         description="Session ID to link multi-turn conversations"
#     )
#
#     # Optional parameters
#     attachments: Optional[List[str]] = Route.vector_store(
#         description="Additional files for RAG"
#     )
#     structured_output_schema: Optional[str] = Route.structured_output(
#         description="JSON Schema for structured output (optional)"
#     )
#     temperature: Optional[float] = Route.adapter(
#         default=1.0, description="Sampling temperature (0-2)"
#     )
#     reasoning_effort: Optional[str] = Route.adapter(
#         default="low",
#         description="Controls reasoning effort (low/medium/high) for mini models",
#     )

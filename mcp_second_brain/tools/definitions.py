"""Tool definitions for all supported models."""

from __future__ import annotations
from typing import List, Optional
from .base import ToolSpec
from .descriptors import Route
from .registry import tool

# Import tools to ensure registration
from . import search_memory  # noqa: F401
# Note: search_attachments is not imported here to prevent MCP exposure
# It remains available for internal model function calling


@tool
class ChatWithGemini25Pro(ToolSpec):
    """Deep multimodal analysis and complex reasoning (Gemini 2.5 Pro, ~1M context).
    Excels at: bug fixing, code analysis, multimodal understanding.

    Example usage:
    - instructions: "Analyze this codebase architecture and identify potential performance bottlenecks"
    - output_format: "Provide a structured analysis with: 1) Architecture overview 2) Identified bottlenecks 3) Recommendations"
    - context: ["/project/src", "/project/tests"]
    - temperature: 0.2 (default, for consistent analysis)"""

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
    instructions: str = Route.prompt(
        pos=0, description="Task instructions for the model"
    )
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(
        pos=2, description="List of file/directory paths to include"
    )
    temperature: Optional[float] = Route.adapter(
        default=0.2, description="Sampling temperature"
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
    instructions: str = Route.prompt(
        pos=0, description="Task instructions for the model"
    )
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(
        pos=2, description="List of file/directory paths to include"
    )
    temperature: Optional[float] = Route.adapter(
        default=0.3, description="Sampling temperature"
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
        pos=2, description="List of file/directory paths to include"
    )
    session_id: str = Route.session(
        description="Session ID for multi-turn conversations"
    )
    # Optional parameters with defaults
    attachments: Optional[List[str]] = Route.vector_store(
        description="Files for vector store (RAG)"
    )
    reasoning_effort: Optional[str] = Route.adapter(
        default="medium", description="Controls reasoning effort (low/medium/high)"
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
        pos=2, description="List of file/directory paths to include"
    )
    session_id: str = Route.session(
        description="Session ID for multi-turn conversations"
    )
    # Optional parameters with defaults
    attachments: Optional[List[str]] = Route.vector_store(
        description="Files for vector store (RAG)"
    )
    reasoning_effort: Optional[str] = Route.adapter(
        default="high", description="Controls reasoning effort (low/medium/high)"
    )
    max_reasoning_tokens: Optional[int] = Route.adapter(
        default=None, description="Maximum reasoning tokens"
    )


@tool
class ChatWithGPT4_1(ToolSpec):
    """Fast long-context processing with web search (GPT-4.1, ~1M context).
    Excels at: large-scale refactoring, codebase navigation, RAG workflows, current information retrieval.

    Example usage:
    - instructions: "Refactor this codebase to use modern React patterns and hooks"
    - output_format: "Migration guide with: 1) Files to change 2) Specific refactoring steps 3) Testing checklist"
    - context: ["/project/src/components"]
    - attachments: ["/project/legacy"] (optional, for RAG on large codebases)
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
        pos=2, description="List of file/directory paths to include"
    )
    session_id: str = Route.session(
        description="Session ID for multi-turn conversations"
    )
    # Optional parameters with defaults
    attachments: Optional[List[str]] = Route.vector_store(
        description="Files for vector store (RAG)"
    )
    temperature: Optional[float] = Route.adapter(
        default=0.2, description="Sampling temperature"
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
        pos=2, description="List of file/directory paths to include"
    )
    session_id: str = Route.session(
        description="Session ID for multi-turn conversations"
    )
    # Optional parameters with defaults
    attachments: Optional[List[str]] = Route.vector_store(
        description="Files for vector store (RAG)"
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
        pos=2, description="List of file/directory paths to include"
    )
    session_id: str = Route.session(
        description="Session ID for multi-turn conversations"
    )
    # Optional parameters with defaults
    attachments: Optional[List[str]] = Route.vector_store(
        description="Files for vector store (RAG)"
    )

"""Tool definitions for all supported models."""
from typing import List, Optional, Literal
from .base import ToolSpec
from .descriptors import Route
from .registry import tool


@tool
class VertexGemini25Pro(ToolSpec):
    """Deep multimodal analysis and complex reasoning (Gemini 2.5 Pro, ~1M context).
    Excels at: bug fixing, code analysis, multimodal understanding."""
    
    model_name = "gemini-2.5-pro"
    adapter_class = "vertex"
    context_window = 1_000_000
    timeout = 600
    
    # Parameters
    instructions: str = Route.prompt(pos=0, description="Task instructions for the model")
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(pos=2, description="List of file/directory paths to include")
    temperature: Optional[float] = Route.adapter(default=0.2, description="Sampling temperature")


@tool
class VertexGemini25Flash(ToolSpec):
    """Fast summarization and quick analysis (Gemini 2.5 Flash, ~1M context).
    Excels at: rapid insights, triage, quick summaries."""
    
    model_name = "gemini-2.5-flash"
    adapter_class = "vertex"
    context_window = 1_000_000
    timeout = 300
    
    # Parameters
    instructions: str = Route.prompt(pos=0, description="Task instructions for the model")
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(pos=2, description="List of file/directory paths to include")
    temperature: Optional[float] = Route.adapter(default=0.3, description="Sampling temperature")


@tool
class OpenAIO3Reasoning(ToolSpec):
    """Chain-of-thought reasoning and algorithm design (OpenAI o3, ~200k context).
    Excels at: step-by-step problem solving, algorithm design, code generation."""
    
    model_name = "o3"
    adapter_class = "openai"
    context_window = 200_000
    timeout = 600
    
    # Parameters
    instructions: str = Route.prompt(pos=0, description="Task instructions for the model")
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(pos=2, description="List of file/directory paths to include")
    attachments: Optional[List[str]] = Route.vector_store(description="Files for vector store (RAG)")
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = Route.adapter(
        default="medium", 
        description="Controls reasoning effort"
    )
    session_id: Optional[str] = Route.session(description="Session ID for multi-turn conversations")


@tool
class OpenAIO3ProDeepAnalysis(ToolSpec):
    """Deep analysis and formal reasoning (OpenAI o3-pro, ~200k context).
    Excels at: formal proofs, complex debugging, architectural analysis.
    Note: Can take 10-30 minutes for deep reasoning."""
    
    model_name = "o3-pro"
    adapter_class = "openai"
    context_window = 200_000
    timeout = 2700  # 45 minutes
    
    # Parameters
    instructions: str = Route.prompt(pos=0, description="Task instructions for the model")
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(pos=2, description="List of file/directory paths to include")
    attachments: Optional[List[str]] = Route.vector_store(description="Files for vector store (RAG)")
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = Route.adapter(
        default="high", 
        description="Controls reasoning effort"
    )
    max_reasoning_tokens: Optional[int] = Route.adapter(description="Maximum reasoning tokens")
    session_id: Optional[str] = Route.session(description="Session ID for multi-turn conversations")


@tool
class OpenAIGPT4LongContext(ToolSpec):
    """Fast long-context processing (GPT-4.1, ~1M context).
    Excels at: large-scale refactoring, codebase navigation, RAG workflows."""
    
    model_name = "gpt-4.1"
    adapter_class = "openai"
    context_window = 1_000_000
    timeout = 300
    
    # Parameters
    instructions: str = Route.prompt(pos=0, description="Task instructions for the model")
    output_format: str = Route.prompt(pos=1, description="Desired output format")
    context: List[str] = Route.prompt(pos=2, description="List of file/directory paths to include")
    attachments: Optional[List[str]] = Route.vector_store(description="Files for vector store (RAG)")
    temperature: Optional[float] = Route.adapter(default=0.2, description="Sampling temperature")
    session_id: Optional[str] = Route.session(description="Session ID for multi-turn conversations")


# For now, we'll handle aliases differently - in the integration layer
# rather than creating duplicate classes
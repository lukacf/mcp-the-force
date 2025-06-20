"""Example tool definitions using actual dataclasses."""
from dataclasses import dataclass
from typing import List, Optional, Literal
from .dataclass_base import ToolSpec, RouteField
from .registry import tool


@tool(aliases=["deep-multimodal-reasoner"])
@dataclass
class VertexGemini25ProDataclass(ToolSpec):
    """Deep multimodal analysis and complex reasoning (Gemini 2.5 Pro, ~1M context).
    Excels at: bug fixing, code analysis, multimodal understanding."""
    
    # Class attributes for model config
    model_name = "gemini-2.5-pro"
    adapter_class = "vertex"
    context_window = 1_000_000
    timeout = 600
    
    # Custom prompt template
    prompt_template = """<task_instructions>
{instructions}
</task_instructions>

<expected_output_format>
{output_format}
</expected_output_format>

<context_information>
{context}
</context_information>"""
    
    # Instance fields with routing metadata
    instructions: str = RouteField.prompt(pos=0, description="Task instructions for the model")
    output_format: str = RouteField.prompt(pos=1, description="Desired output format")
    context: List[str] = RouteField.prompt(pos=2, description="List of file/directory paths to include")
    temperature: Optional[float] = RouteField.adapter(description="Sampling temperature", default=0.2)
    session_id: Optional[str] = RouteField.session(description="Session ID (ignored for Gemini)", default=None)


@tool(aliases=["chain-of-thought-helper"]) 
@dataclass
class OpenAIO3ReasoningDataclass(ToolSpec):
    """Chain-of-thought reasoning and algorithm design (OpenAI o3, ~200k context).
    Excels at: step-by-step problem solving, algorithm design, code generation."""
    
    # Class attributes
    model_name = "o3"
    adapter_class = "openai"
    context_window = 200_000
    timeout = 600
    
    # Custom prompt template
    prompt_template = """## Task Instructions
{instructions}

## Output Requirements
{output_format}

## Provided Context
{context}

Please approach this task step-by-step, showing your reasoning process."""
    
    # Instance fields
    instructions: str = RouteField.prompt(pos=0, description="Task instructions for the model")
    output_format: str = RouteField.prompt(pos=1, description="Desired output format")
    context: List[str] = RouteField.prompt(pos=2, description="List of file/directory paths to include")
    attachments: Optional[List[str]] = RouteField.vector_store(
        description="Files for vector store (RAG)", 
        default=None
    )
    reasoning_effort: Optional[Literal["low", "medium", "high"]] = RouteField.adapter(
        description="Controls reasoning effort",
        default="medium"
    )
    session_id: Optional[str] = RouteField.session(
        description="Session ID for multi-turn conversations",
        default=None
    )


# Comparison with descriptor-based approach:
# Pros of dataclass approach:
# - Uses standard Python dataclasses - more familiar to developers
# - Better IDE support and type checking
# - Less magic, more explicit
# - Can leverage all dataclass features (frozen, slots, etc.)
#
# Cons of dataclass approach:
# - Requires @dataclass decorator in addition to @tool
# - Slightly more verbose field definitions
# - Mixing class and instance attributes can be confusing
# - Need wrapper functions (RouteField.xxx) instead of simple Route.xxx()
#
# The descriptor approach is arguably cleaner for this specific use case,
# but the dataclass approach is more standard Python.
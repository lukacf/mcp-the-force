"""Prompt engine for template-based prompt generation."""

import logging
from typing import Dict, Any, Type
from .base import ToolSpec

logger = logging.getLogger(__name__)

# Default template that mimics current behavior
DEFAULT_PROMPT_TEMPLATE = """<instructions>
{instructions}
</instructions>

<output_format>
{output_format}
</output_format>

<file_context>
{context}
</file_context>"""


class PromptEngine:
    """Handles prompt generation using templates."""

    def __init__(self, default_template: str = DEFAULT_PROMPT_TEMPLATE):
        """Initialize with a default template.

        Args:
            default_template: Default template to use when tool doesn't provide one
        """
        self.default_template = default_template

    async def build(
        self, spec_class: Type[ToolSpec], prompt_params: Dict[str, Any]
    ) -> str:
        """Build prompt using tool's template or default.

        Args:
            spec_class: The tool specification class
            prompt_params: Parameters routed to prompt

        Returns:
            Formatted prompt string
        """
        # Get template from tool or use default
        template = getattr(spec_class, "prompt_template", None) or self.default_template

        # Handle the current special case for context
        # Convert list of paths to string if needed
        if "context" in prompt_params and isinstance(prompt_params["context"], list):
            if prompt_params["context"]:
                # Use the existing build_prompt utility for now
                # This maintains backward compatibility
                from ..utils.prompt_builder import build_prompt
                import asyncio

                instructions = prompt_params.get("instructions", "")
                output_format = prompt_params.get("output_format", "")
                context = prompt_params.get("context", [])

                # Get model name from spec_class if available
                model_name = getattr(spec_class, "model_name", None)

                prompt, _ = await asyncio.to_thread(
                    build_prompt,
                    instructions,
                    output_format,
                    context,
                    None,  # Attachments handled separately via vector store
                    model_name,  # Pass model name for context limits
                )
                return prompt
            else:
                prompt_params["context"] = ""

        # Format the template with available parameters
        try:
            # Provide safe defaults for missing parameters
            safe_params = {
                "instructions": "",
                "output_format": "",
                "context": "",
                **prompt_params,
            }

            prompt = template.format(**safe_params)

            # Handle any extra parameters not in template
            extra_params = {k: v for k, v in prompt_params.items() if k not in template}
            if extra_params:
                # Append as XML tags for backward compatibility
                extra_text = "\n".join(
                    f"<{k}>{v}</{k}>" for k, v in extra_params.items()
                )
                prompt = f"{prompt}\n{extra_text}"

            return prompt

        except KeyError as e:
            logger.warning(f"Missing parameter in template: {e}")
            # Fall back to a simple format
            return "\n".join(f"{k}: {v}" for k, v in prompt_params.items())


# Global instance
prompt_engine = PromptEngine()

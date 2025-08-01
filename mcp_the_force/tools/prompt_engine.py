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
            # Context is handled by the executor via build_context_with_stable_list
            # This should never be reached with the current architecture
            logger.warning("Unexpected list context in prompt_engine - this is a bug")
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
            extra_params = {
                k: v for k, v in prompt_params.items() if k not in safe_params
            }
            if extra_params:
                # Use lxml to create proper XML for extra parameters
                try:
                    from lxml import etree

                    extras_root = etree.Element("extra_parameters")
                    for k, v in extra_params.items():
                        elem = etree.SubElement(extras_root, k)
                        elem.text = str(v)
                    extra_text = etree.tostring(
                        extras_root, encoding="unicode", pretty_print=True
                    )
                    prompt = f"{prompt}\n{extra_text}"
                except ImportError:
                    # Fallback if lxml not available
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

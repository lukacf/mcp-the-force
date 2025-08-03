"""XML prompt construction for optimized context."""

import logging
from typing import List, Tuple, Any
from xml.etree import ElementTree as ET

from ..utils.file_tree import build_file_tree_from_paths
from ..utils.token_counter import count_tokens

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds XML prompts with proper token accounting."""

    def __init__(self):
        pass

    def build_prompt(
        self,
        instructions: str,
        output_format: str,
        inline_files: List[Tuple[str, str, int]],  # (path, content, tokens)
        all_files: List[str],
        overflow_files: List[str],
    ) -> str:
        """Build complete XML prompt structure.

        Args:
            instructions: User instructions
            output_format: Desired output format
            inline_files: Files to include inline as (path, content, tokens)
            all_files: All requested file paths
            overflow_files: Files that go to vector store

        Returns:
            Complete XML prompt string
        """
        # Build XML structure
        task = ET.Element("Task")
        ET.SubElement(task, "Instructions").text = instructions
        ET.SubElement(task, "OutputFormat").text = output_format

        # Add file map with proper attachment markers
        file_map = ET.SubElement(task, "file_map")
        file_tree = build_file_tree_from_paths(
            all_paths=all_files,
            attachment_paths=overflow_files,
            root_path=None,
        )
        file_map.text = (
            file_tree
            + "\\n\\nLegend: Files marked 'attached' are available via search_task_files. Unmarked files are included below."
        )

        # Add inline file contents
        ctx = ET.SubElement(task, "CONTEXT")
        for path, content, _ in inline_files:
            ctx.append(self._create_file_element(path, content))

        # Convert to string
        prompt = ET.tostring(task, encoding="unicode")

        # Add vector store instructions if needed
        if overflow_files:
            prompt += "\\n\\n<instructions_on_use>The files in the file tree but not included in <CONTEXT> you access via the search_task_files MCP function. They are stored in a vector database and the search function does semantic search.</instructions_on_use>"

        return prompt

    def _create_file_element(self, path: str, content: str) -> Any:
        """Create XML file element with sanitized content."""
        el = ET.Element("file", path=path)
        # Sanitize content to remove control characters except tabs, newlines, returns
        safe_content = "".join(c for c in content if ord(c) >= 32 or c in "\\t\\n\\r")
        el.text = safe_content
        return el

    def calculate_complete_prompt_tokens(
        self, developer_prompt: str, user_prompt: str
    ) -> int:
        """Calculate tokens for complete prompt sent to model."""
        return count_tokens([developer_prompt, user_prompt])

    def file_wrapper_tokens(self, file_path: str) -> int:
        """Calculate tokens for XML wrapper tags around a file."""
        from ..utils.token_utils import file_wrapper_tokens

        return file_wrapper_tokens(file_path)

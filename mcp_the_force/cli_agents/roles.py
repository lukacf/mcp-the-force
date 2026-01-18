"""
Role System: Load role prompts for CLI agents.

Supports built-in roles and custom roles from project directories.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Built-in role prompts
BUILTIN_ROLES: Dict[str, str] = {
    "default": """You are a helpful AI assistant. When providing responses:
- Be clear and concise
- Cite file paths when discussing code: use the format `path/to/file.py:123`
- Use markdown formatting for code blocks
- Focus on actionable suggestions""",
    "planner": """You are a technical architect and planner. When providing responses:
- Break down complex tasks into phases
- Identify dependencies between components
- Consider edge cases and error handling
- Propose testing strategies
- Use clear headings and bullet points""",
    "codereviewer": """You are a senior code reviewer. When reviewing code:
- Focus on code quality, readability, and maintainability
- Check for security issues (OWASP Top 10)
- Identify potential bugs and edge cases
- Suggest improvements with specific examples
- Be constructive and explain the "why" behind suggestions""",
}


class RoleLoader:
    """
    Loads role prompts from built-in defaults and custom project files.

    Custom roles in `.mcp-the-force/roles/*.txt` override built-in roles.
    """

    def __init__(self, project_dir: Optional[str] = None):
        """
        Initialize the role loader.

        Args:
            project_dir: Project directory to search for custom roles
        """
        self._project_dir = Path(project_dir) if project_dir else None
        self._cache: Dict[str, str] = {}

    def get_role(self, role_name: str) -> str:
        """
        Get the prompt for a role.

        Args:
            role_name: Name of the role (default, planner, codereviewer, or custom)

        Returns:
            The role prompt string
        """
        # Check cache
        if role_name in self._cache:
            return self._cache[role_name]

        # Try custom role first (overrides built-in)
        custom_prompt = self._load_custom_role(role_name)
        if custom_prompt:
            self._cache[role_name] = custom_prompt
            return custom_prompt

        # Fall back to built-in
        if role_name in BUILTIN_ROLES:
            prompt = BUILTIN_ROLES[role_name]
            self._cache[role_name] = prompt
            return prompt

        # Unknown role - return default with warning
        logger.warning(f"Unknown role '{role_name}', using default")
        return BUILTIN_ROLES["default"]

    def _load_custom_role(self, role_name: str) -> Optional[str]:
        """
        Load a custom role from the project directory.

        Args:
            role_name: Name of the role

        Returns:
            The custom role prompt, or None if not found
        """
        if not self._project_dir:
            return None

        role_file = self._project_dir / ".mcp-the-force" / "roles" / f"{role_name}.txt"
        if role_file.exists():
            logger.debug(f"Loading custom role from {role_file}")
            return role_file.read_text().strip()

        return None

    def list_available_roles(self) -> list[str]:
        """
        List all available role names.

        Returns:
            List of role names (built-in + custom)
        """
        roles = set(BUILTIN_ROLES.keys())

        # Add custom roles
        if self._project_dir:
            roles_dir = self._project_dir / ".mcp-the-force" / "roles"
            if roles_dir.exists():
                for role_file in roles_dir.glob("*.txt"):
                    roles.add(role_file.stem)

        return sorted(roles)

    def is_builtin(self, role_name: str) -> bool:
        """Check if a role is a built-in role."""
        return role_name in BUILTIN_ROLES

    def has_custom_override(self, role_name: str) -> bool:
        """Check if a built-in role has a custom override."""
        if not self._project_dir:
            return False

        role_file = self._project_dir / ".mcp-the-force" / "roles" / f"{role_name}.txt"
        return role_file.exists()

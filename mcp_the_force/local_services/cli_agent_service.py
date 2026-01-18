"""
CLIAgentService: LocalService for work_with tool.

Orchestrates CLI agent execution via subprocess.
"""

from typing import Any, List, Optional


class CLIAgentService:
    """
    Service for executing CLI agents (Claude, Gemini, Codex).

    Implements the LocalService pattern for work_with tool:
    - Builds isolated environment
    - Constructs CLI command with appropriate flags
    - Executes subprocess
    - Parses output and extracts session ID
    - Stores session mapping for resume
    - Returns summarized response
    """

    async def execute(
        self,
        agent: str,
        task: str,
        session_id: str,
        role: str,
        context: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Execute a CLI agent.

        Args:
            agent: CLI agent name (claude, gemini, codex)
            task: Task/prompt for the agent
            session_id: Force session ID
            role: Role name for system prompt
            context: Optional list of context file/directory paths
            **kwargs: Additional parameters

        Returns:
            Summarized response from the CLI agent
        """
        raise NotImplementedError("CLIAgentService.execute not implemented")


class ConsultationService:
    """
    Service for consult_with tool.

    Routes to internal chat_with_* tools based on model parameter.
    """

    async def execute(
        self,
        model: str,
        question: str,
        session_id: str,
        output_format: str,
        **kwargs: Any,
    ) -> str:
        """
        Execute a consultation with an API model.

        Args:
            model: Model identifier (gpt52, gemini3_pro, etc.)
            question: Question/prompt for the model
            session_id: Force session ID
            output_format: Desired output format
            **kwargs: Additional parameters

        Returns:
            Response from the model
        """
        raise NotImplementedError("ConsultationService.execute not implemented")

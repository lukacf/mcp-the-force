"""
CLIAgentService: LocalService for work_with tool.

Orchestrates CLI agent execution via subprocess.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from mcp_the_force.cli_agents.availability import (
    CLIAvailabilityChecker,
    CLINotAvailableError,
)
from mcp_the_force.cli_agents.compactor import Compactor
from mcp_the_force.cli_agents.environment import EnvironmentBuilder
from mcp_the_force.cli_agents.executor import CLIExecutor
from mcp_the_force.cli_agents.model_cli_resolver import (
    ModelNotFoundError,
    NoCLIAvailableError,
    resolve_model_to_cli,
)
from mcp_the_force.cli_agents.output_cleaner import OutputCleaner, OutputFileHandler
from mcp_the_force.cli_agents.roles import RoleLoader
from mcp_the_force.cli_agents.session_bridge import SessionBridge
from mcp_the_force.cli_agents.summarizer import OutputSummarizer
from mcp_the_force.cli_plugins.registry import get_cli_plugin
from mcp_the_force.unified_session_cache import UnifiedSessionCache

logger = logging.getLogger(__name__)


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

    def __init__(self, project_dir: Optional[str] = None):
        """Initialize the CLI agent service."""
        self._project_dir = project_dir or "/tmp"
        self._availability_checker = CLIAvailabilityChecker()
        self._compactor = Compactor()
        self._environment_builder = EnvironmentBuilder()
        self._executor = CLIExecutor()
        self._output_cleaner = OutputCleaner()
        self._output_file_handler = OutputFileHandler()
        self._session_bridge = SessionBridge()
        self._role_loader = RoleLoader(project_dir=project_dir)
        self._summarizer = OutputSummarizer()

    async def execute(
        self,
        agent: str,
        task: str,
        session_id: str,
        role: str = "default",
        reasoning_effort: str = "medium",
        cli_flags: Optional[List[str]] = None,
        timeout: int = 14400,
        **_kwargs: Any,
    ) -> str:
        """
        Execute a CLI agent.

        Args:
            agent: Model name (e.g., "gpt-5.2", "claude-sonnet-4-5") - resolves to CLI
            task: Task/prompt for the agent
            session_id: Force session ID
            role: Role name for system prompt (default, planner, codereviewer)
            reasoning_effort: Reasoning effort level (low/medium/high/xhigh)
            cli_flags: Optional additional CLI flags for power users
            timeout: Execution timeout in seconds
            **kwargs: Additional parameters

        Returns:
            Summarized response from the CLI agent

        Raises:
            ModelNotFoundError: If the model is not in the registry
            NoCLIAvailableError: If the model exists but has no CLI mapping
            CLINotAvailableError: If the CLI is not installed
        """
        logger.debug(f"CLIAgentService.execute: agent={agent}, session_id={session_id}")

        # 1. Resolve model→CLI
        try:
            cli_name = resolve_model_to_cli(agent)
        except (ModelNotFoundError, NoCLIAvailableError):
            raise

        # 2. Get CLI plugin
        cli_plugin = get_cli_plugin(cli_name)
        if cli_plugin is None:
            raise ValueError(f"No CLI plugin registered for: {cli_name}")

        # 3. Check CLI availability
        if not self._availability_checker.is_available(cli_name):
            raise CLINotAvailableError(cli_name)

        # 4. Check SessionBridge for existing CLI session (for resume)
        # Use project basename for consistent lookups
        project_name = (
            os.path.basename(self._project_dir) if self._project_dir else "default"
        )
        existing_cli_session = await self._session_bridge.get_cli_session_id(
            project=project_name,
            session_id=session_id,
            cli_name=cli_name,
        )

        # 4b. Check for existing cross-tool history (for context injection)
        existing_session = await UnifiedSessionCache.get_session(
            project=project_name,
            session_id=session_id,
        )
        existing_history = existing_session.history if existing_session else []
        context_injected = False
        context_source = None

        # 4c. Determine if we should use --resume or start fresh with context injection
        # Rule: Only use --resume if the PREVIOUS turn was from the same CLI
        # This ensures cross-tool context is always visible when switching tools
        use_resume = False
        logger.info(
            f"[CLI-SERVICE] Session {session_id}: "
            f"history={len(existing_history)} turns, "
            f"cli_session={existing_cli_session or 'none'}"
        )

        if existing_cli_session and existing_history:
            # Check if the last assistant turn was from this CLI
            last_assistant_turn = None
            for turn in reversed(existing_history):
                if turn.get("role") == "assistant":
                    last_assistant_turn = turn
                    break
            if last_assistant_turn:
                last_tool = last_assistant_turn.get("tool", "")
                # Check if it was work_with (CLI) - could be "work_with" or have cli metadata
                last_cli = last_assistant_turn.get("metadata", {}).get("cli_name", "")
                # Use resume only if last turn was from same CLI tool
                if last_tool == "work_with" and (last_cli == cli_name or not last_cli):
                    # If no cli_name metadata, check if there's been any other tool use
                    # by seeing if all work_with turns could have been this CLI
                    use_resume = True
                    logger.info(
                        f"[CLI-SERVICE] Using --resume: last turn was same CLI ({cli_name})"
                    )
                else:
                    logger.info(
                        f"[CLI-SERVICE] NOT resuming: last turn was {last_tool} "
                        f"(cli={last_cli}), current={cli_name}"
                    )
            else:
                # No assistant turns yet, can use resume if CLI session exists
                use_resume = True
                logger.info("[CLI-SERVICE] Using --resume: no assistant turns yet")
        elif existing_cli_session and not existing_history:
            # CLI session exists but no history (edge case) - use resume
            use_resume = True
            logger.info("[CLI-SERVICE] Using --resume: CLI session exists, no history")
        else:
            logger.info("[CLI-SERVICE] Fresh session, no resume available")

        # If there's history and we're NOT using resume, inject compacted context
        if existing_history and not use_resume:
            # Determine context source (first turn's tool, or "mixed")
            tools_in_history = set(
                turn.get("tool") for turn in existing_history if turn.get("tool")
            )
            if len(tools_in_history) == 1:
                context_source = list(tools_in_history)[0]
            elif tools_in_history:
                context_source = "mixed"

            logger.info(
                f"[CLI-SERVICE] Cross-tool handoff: injecting context from {context_source} "
                f"({len(existing_history)} turns)"
            )

            # Compact history for CLI context injection
            # Compactor always targets 30k tokens regardless of max_tokens
            compacted = await self._compactor.compact_for_cli(
                history=existing_history,
                target_cli=cli_name,
                max_tokens=0,  # Ignored, compactor uses fixed TARGET_TOKENS
            )
            if compacted:
                # Inject compacted context as task prefix
                task = f"{compacted}\n\nCurrent task: {task}"
                context_injected = True
                logger.info(
                    f"[CLI-SERVICE] Context injected: {len(compacted)} chars prepended to task"
                )

        # 5. Auto-inject project directory into task to guide the agent
        # The project_dir comes from config file location (parent of .mcp-the-force folder)
        if self._project_dir and self._project_dir != "/tmp":
            task = f"Work from this directory: {self._project_dir}\n\n{task}"
            logger.info(
                f"[CLI-SERVICE] Auto-injected project dir into task: {self._project_dir}"
            )

        # 6. Load role prompt
        role_prompt = self._role_loader.get_role(role)

        # 7. Build command (passing reasoning_effort to plugin)
        if use_resume and existing_cli_session:
            # Resume existing session
            command = cli_plugin.build_resume_args(
                session_id=existing_cli_session,
                task=task,
                reasoning_effort=reasoning_effort,
            )
        else:
            # New session - automatically add project directory as context
            context_dirs = (
                [self._project_dir]
                if self._project_dir and self._project_dir != "/tmp"
                else []
            )
            command = cli_plugin.build_new_session_args(
                task=task,
                context_dirs=context_dirs,
                role=role_prompt,
                reasoning_effort=reasoning_effort,
            )

        # Add CLI executable at the front
        full_command = [cli_plugin.executable] + command

        # Add user-provided CLI flags
        if cli_flags:
            full_command.extend(cli_flags)

        # 7. Build isolated environment
        env = self._environment_builder.build_isolated_env(
            project_dir=self._project_dir,
            cli_name=cli_name,
        )

        # 7b. Get and merge reasoning effort env vars (e.g., MAX_THINKING_TOKENS for Claude)
        if hasattr(cli_plugin, "get_reasoning_env_vars"):
            reasoning_env = cli_plugin.get_reasoning_env_vars(reasoning_effort)
            if reasoning_env:
                env.update(reasoning_env)
                logger.info(
                    f"[CLI-SERVICE] Added reasoning env vars: {list(reasoning_env.keys())}"
                )

        # 8. Execute via CLIExecutor
        logger.info(f"Executing CLI agent: {cli_name} for session {session_id}")
        result = await self._executor.execute(
            command=full_command,
            env=env,
            timeout=timeout,
            cwd=self._project_dir,
        )

        # 9. Parse response via CLI plugin
        parsed = cli_plugin.parse_output(result.stdout)

        # 10. Store CLI session mapping (for future resume)
        if parsed.session_id:
            await self._session_bridge.store_cli_session_id(
                project=project_name,
                session_id=session_id,
                cli_name=cli_name,
                cli_session_id=parsed.session_id,
            )

        # 11. Build result content
        # Use parsed.content (already cleaned by parser) as primary source
        # Fall back to raw stdout only if parsed content is empty
        raw_output = parsed.content or result.stdout or ""
        if result.timed_out:
            raw_output += "\n\n[CLI execution timed out - partial output shown]"
        if result.idle_timeout:
            raw_output += "\n\n[CLI process killed due to idle timeout - may be hung]"
        if result.return_code != 0 and not result.stdout and not parsed.content:
            raw_output = f"CLI error (exit code {result.return_code}):\n{result.stderr}"

        # 11b. Clean the output (convert JSONL to markdown, count tokens)
        cleaned = self._output_cleaner.clean(raw_output)

        # 12. Handle large outputs: save to file, summarize, include link
        if cleaned.exceeds_threshold:
            # Save full output to file
            output_file = self._output_file_handler.save_to_file(
                cleaned.markdown, session_id=session_id
            )

            # Summarize the cleaned output
            summarized = await self._summarizer.summarize(
                output=cleaned.markdown,
                task_context=f"Task: {task}",
            )

            # Format response with summary and file link
            if summarized and summarized != cleaned.markdown:
                final_response = self._output_file_handler.format_summary_with_link(
                    summarized, output_file
                )
            else:
                # Summarization failed or returned same content - return cleaned with file link
                final_response = self._output_file_handler.format_summary_with_link(
                    cleaned.markdown[:5000] + "\n\n... (output truncated)", output_file
                )
        else:
            # Small output: return cleaned markdown directly
            final_response = cleaned.markdown

        # 13. Store turn in UnifiedSessionCache with metadata
        turn_metadata: Dict[str, Any] = {
            "cli_name": cli_name
        }  # Always store which CLI was used
        if context_injected:
            turn_metadata["context_injected"] = True
            if context_source:
                turn_metadata["context_source"] = context_source
        if use_resume and existing_cli_session:
            turn_metadata["resumed_from"] = existing_cli_session
            turn_metadata["used_resume_flag"] = True

        # Append user turn (task) and assistant turn (response) to history
        await UnifiedSessionCache.append_message(
            project=project_name,
            session_id=session_id,
            message={
                "role": "user",
                "content": task,
                "tool": "work_with",
            },
        )
        await UnifiedSessionCache.append_message(
            project=project_name,
            session_id=session_id,
            message={
                "role": "assistant",
                "content": final_response,
                "tool": "work_with",
                "metadata": turn_metadata if turn_metadata else None,
            },
        )

        return final_response


class ConsultationService:
    """
    Service for consult_with tool.

    Routes to internal chat_with_* tools based on model parameter.
    """

    def __init__(self, project_dir: Optional[str] = None):
        """Initialize the consultation service."""
        self._project_dir = project_dir or "/tmp"
        self._compactor = Compactor()

    async def execute(
        self,
        model: str,
        question: str,
        session_id: str,
        output_format: str,
        context: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Execute a consultation with an API model.

        Args:
            model: Model identifier (gpt52, gemini3_pro, etc.)
            question: Question/prompt for the model
            session_id: Force session ID
            output_format: Desired output format
            context: Optional file paths for context
            **kwargs: Additional parameters

        Returns:
            Response from the model

        Raises:
            ValueError: If the model is not found in the registry
        """
        from mcp_the_force.tools.registry import list_tools
        from mcp_the_force.tools.executor import executor

        # Ensure registry is populated
        list_tools()

        # Resolve model to tool name
        tool_metadata = self._resolve_model_tool(model)
        if tool_metadata is None:
            raise ValueError(f"Unknown model: {model}")

        # Check for existing cross-tool history (for context injection)
        project_name = (
            os.path.basename(self._project_dir) if self._project_dir else "default"
        )
        existing_session = await UnifiedSessionCache.get_session(
            project=project_name,
            session_id=session_id,
        )
        existing_history = existing_session.history if existing_session else []

        # If there's history from other tools, compact and inject
        if existing_history:
            # Determine context source (first turn's tool, or "mixed")
            tools_in_history = set(
                turn.get("tool") for turn in existing_history if turn.get("tool")
            )
            context_source = None
            if len(tools_in_history) == 1:
                context_source = list(tools_in_history)[0]
            elif tools_in_history:
                context_source = "mixed"

            # Compact history for API context injection
            # Compactor always targets 30k tokens regardless of max_tokens
            compacted = await self._compactor.compact_for_cli(
                history=existing_history,
                target_cli="api",  # Generic target for API models
                max_tokens=0,  # Ignored, compactor uses fixed TARGET_TOKENS
            )
            if compacted:
                # Inject compacted context as question prefix
                question = f"{compacted}\n\nCurrent question: {question}"
                logger.debug(
                    f"Injected {len(existing_history)} turns from {context_source} into consult_with"
                )

        # Execute the tool via executor
        try:
            response = await executor.execute(
                metadata=tool_metadata,
                instructions=question,
                output_format=output_format,
                session_id=session_id,
                context=context,
                **kwargs,
            )

            # Store this conversation turn in session history
            await UnifiedSessionCache.append_message(
                project=project_name,
                session_id=session_id,
                message={
                    "role": "user",
                    "content": question,
                    "tool": "consult_with",
                },
            )
            await UnifiedSessionCache.append_message(
                project=project_name,
                session_id=session_id,
                message={
                    "role": "assistant",
                    "content": response or "",
                    "tool": "consult_with",
                    "metadata": {"model": model},
                },
            )

            return response or ""
        except Exception as e:
            logger.error(f"ConsultationService.execute failed: {e}")
            raise

    def _resolve_model_tool(self, model: str) -> Any:
        """
        Resolve user-friendly model name to registered tool.

        Tries multiple patterns:
        1. Direct lookup: "chat_with_{model}"
        2. Normalized versions (remove dots, dashes)

        Args:
            model: User-provided model name (gpt-5.2, gemini3_pro, etc.)

        Returns:
            ToolMetadata if found, None otherwise
        """
        from mcp_the_force.tools.registry import get_tool

        # Generate variations of the model name
        # gpt-5.2 -> gpt52, gpt_52, gpt5.2, etc.
        variations = [
            model,
            model.replace("-", "").replace(".", ""),  # gpt-5.2 -> gpt52
            model.replace("-", "_"),  # gpt-5.2 -> gpt_5.2
            model.replace(".", ""),  # gpt-5.2 -> gpt-52
            model.replace("-", "_").replace(".", ""),  # gpt-5.2 -> gpt_52
            model.lower(),
            model.lower().replace("-", "").replace(".", ""),
        ]

        # Try each variation with chat_with_ prefix
        for var in variations:
            tool_name = f"chat_with_{var}"
            metadata = get_tool(tool_name)
            if metadata:
                return metadata

        return None

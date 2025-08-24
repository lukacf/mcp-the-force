"""CollaborationService - Main orchestrator for multi-model collaborations."""

import logging
from typing import Optional, Literal, TYPE_CHECKING
import json
import time

if TYPE_CHECKING:
    from fastmcp import Context
from datetime import datetime
from pathlib import Path
import os

from ..types.collaboration import (
    CollaborationMessage,
    CollaborationSession,
    CollaborationConfig,
)
from ..tools.executor import ToolExecutor
from ..unified_session_cache import UnifiedSessionCache
from .whiteboard_manager import WhiteboardManager

logger = logging.getLogger(__name__)


class CollaborationService:
    """Orchestrates multi-model collaborations using shared whiteboards."""

    def __init__(
        self,
        executor: Optional[ToolExecutor] = None,
        whiteboard_manager: Optional[WhiteboardManager] = None,
        session_cache: Optional[UnifiedSessionCache] = None,
    ):
        """Initialize CollaborationService with dependencies.

        Args:
            executor: Tool executor instance (optional, will use global)
            whiteboard_manager: Whiteboard manager instance (optional, will create)
            session_cache: Session cache instance (optional, will use global)
        """
        # Use dependency injection for testing, but default to global instances
        if executor is None:
            from ..tools.executor import executor as global_executor

            self.executor = global_executor
        else:
            self.executor = executor

        if whiteboard_manager is None:
            self.whiteboard = WhiteboardManager()
        else:
            self.whiteboard = whiteboard_manager

        if session_cache is None:
            from ..unified_session_cache import unified_session_cache as global_cache

            self.session_cache = global_cache
        else:
            self.session_cache = session_cache

    async def execute(
        self,
        session_id: str,
        objective: str,
        models: list[str],
        user_input: str = "",
        mode: Literal["round_robin", "orchestrator"] = "round_robin",
        max_steps: int = 10,
        config: Optional[CollaborationConfig] = None,
        ctx: Optional["Context"] = None,
        context: Optional[list[str]] = None,
        priority_context: Optional[list[str]] = None,
        **kwargs,
    ) -> str:
        """Main orchestration logic for multi-model collaboration.

        Args:
            session_id: Unique identifier for the collaboration session
            objective: The main task or problem for models to solve collaboratively
            models: List of model tool names to participate
            user_input: Additional input or guidance for the next collaboration turn
            mode: Collaboration style ("round_robin" or "orchestrator")
            max_steps: Maximum number of collaboration turns
            config: Optional configuration override
            ctx: FastMCP Context for progress reporting (optional)
            context: List of file/directory paths for model context (optional)
            priority_context: List of priority file/directory paths (optional)
            **kwargs: Additional parameters (e.g., structured_output_schema from MCP)

        Returns:
            Response from the current collaboration turn
        """
        # Use config defaults if not provided
        if config is None:
            config = CollaborationConfig(max_steps=max_steps, timeout_per_step=300)

        logger.info(
            f"Starting collaboration session {session_id} with {len(models)} models"
        )

        try:
            # Get project name for UnifiedSessionCache
            from ..config import get_settings

            settings = get_settings()
            project = Path(settings.logging.project_path or os.getcwd()).name

            # 1. Load or create collaboration session
            session = await self._get_or_create_session(
                project, session_id, objective, models, mode, config
            )

            # Check if session is completed
            if session.is_completed():
                return f"Collaboration session {session_id} has completed ({session.current_step}/{session.max_steps} steps)."

            # 2. Ensure whiteboard exists
            whiteboard_info = await self.whiteboard.get_or_create_store(session_id)
            logger.debug(
                f"Using whiteboard {whiteboard_info['store_id']} for session {session_id}"
            )

            # 3. Add user input to whiteboard and session
            if user_input.strip():
                user_message = CollaborationMessage(
                    speaker="user",
                    content=user_input,
                    timestamp=datetime.now(),
                    metadata={"step": session.current_step},
                )

                await self.whiteboard.append_message(session_id, user_message)
                session.add_message(user_message)
                logger.debug(f"Added user message to session {session_id}")

                # Also append to UnifiedSessionCache history for describe_session summaries
                await self.session_cache.append_responses_message(
                    project=project,
                    tool="chatter_collaborate",
                    session_id=session_id,
                    role="user",
                    text=user_input[:500],  # Truncate for transcript
                )

            # 4. Optional summarization check before the loop (for very long carry-over sessions)
            if len(session.messages) >= config.summarization_threshold:
                logger.info(
                    f"Triggering summarization for session {session_id} ({len(session.messages)} messages)"
                )
                await self.whiteboard.summarize_and_rollover(
                    session_id, config.summarization_threshold
                )

            # 5. Drive the collaboration automatically until completion
            steps_ran = 0
            last_model = None
            last_response = ""
            start_time = time.time()

            logger.info(
                f"Starting collaboration loop: current_step={session.current_step}, max_steps={session.max_steps}"
            )

            # Write initial progress file for status line
            self._write_progress_file(session, phase="starting", start_time=start_time)

            # Report initial progress (MCP streaming - may not work on stdio)
            if ctx:
                logger.info("[CHATTER] Context available - reporting initial progress")
                await ctx.report_progress(
                    progress=session.current_step,
                    total=session.max_steps,
                    message=f"Starting collaboration with {len(models)} models: {', '.join(models)}",
                )
                logger.info("[CHATTER] Initial progress reported successfully")
            else:
                logger.warning(
                    "[CHATTER] No Context available - progress reporting disabled"
                )
            logger.info(
                f"Starting collaboration with {len(models)} models: {', '.join(models)}"
            )

            while not session.is_completed():
                # Safety: don't exceed configured max steps
                if session.current_step >= session.max_steps:
                    logger.info(
                        f"Reached max steps ({session.max_steps}) for session {session_id}"
                    )
                    break

                # Get next model for progress reporting
                next_model = session.get_next_model()

                # Update progress file BEFORE turn
                self._write_progress_file(
                    session,
                    current_model=next_model,
                    phase=f"thinking ({next_model})",
                    start_time=start_time,
                )

                # Report progress BEFORE turn (MCP streaming - may not work on stdio)
                if ctx:
                    logger.info(
                        f"[CHATTER] Reporting progress before turn: {session.current_step}/{session.max_steps}"
                    )
                    await ctx.report_progress(
                        progress=session.current_step,
                        total=session.max_steps,
                        message=f"Starting turn {session.current_step + 1}/{session.max_steps} with {next_model}",
                    )
                    logger.info("[CHATTER] Progress reported successfully")
                logger.info(
                    f"Starting turn {session.current_step + 1}/{session.max_steps} with {next_model}"
                )

                # Renew lease before each turn for long-thinking models
                await self.whiteboard.vs_manager.renew_lease(f"collab_{session_id}")

                # Enforce timeout per step via executor override in _execute_model_turn
                response = await self._execute_model_turn(
                    session, 
                    whiteboard_info, 
                    config.timeout_per_step,
                    context,
                    priority_context
                )

                # Compose model message and append to whiteboard + session
                model_message = CollaborationMessage(
                    speaker=next_model,
                    content=response,
                    timestamp=datetime.now(),
                    metadata={"step": session.current_step, "mode": session.mode},
                )
                await self.whiteboard.append_message(session_id, model_message)
                session.add_message(model_message)

                # Report progress AFTER turn
                if ctx:
                    await ctx.report_progress(
                        progress=session.current_step + 1,
                        total=session.max_steps,
                        message=f"Completed turn {session.current_step + 1}/{session.max_steps}: {next_model} responded",
                    )
                logger.info(
                    f"Completed turn {session.current_step + 1}/{session.max_steps}: {next_model} responded"
                )

                # Also append to human-readable transcript for describe_session summaries
                await self.session_cache.append_responses_message(
                    project=project,
                    tool="chatter_collaborate",
                    session_id=session_id,
                    role="assistant",
                    text=f"[{next_model}]: {response[:500]}...",
                )

                # Advance state and persist
                session.advance_step()
                await self.session_cache.set_metadata(
                    project,
                    "chatter_collaborate",
                    session_id,
                    "collab_state",
                    session.to_dict(),
                )

                steps_ran += 1
                last_model = next_model
                last_response = response

                # Update progress file AFTER turn
                self._write_progress_file(
                    session,
                    current_model=next_model,
                    phase="completed turn",
                    start_time=start_time,
                )

                logger.info(
                    f"Completed turn {steps_ran} for session {session_id} ({next_model})"
                )

                # Summarize + rollover when message count crosses threshold
                if len(session.messages) >= config.summarization_threshold:
                    logger.info(
                        f"Summarization threshold reached in session {session_id} "
                        f"({len(session.messages)} messages); rolling over"
                    )
                    await self.whiteboard.summarize_and_rollover(
                        session_id, config.summarization_threshold
                    )

            # Report final completion progress
            if ctx:
                await ctx.report_progress(
                    progress=session.current_step,
                    total=session.max_steps,
                    message=f"Collaboration complete! Executed {steps_ran} turns with {len(models)} models",
                )
            logger.info(
                f"Collaboration complete! Executed {steps_ran} turns with {len(models)} models"
            )

            # Update progress file for completion
            self._write_progress_file(session, phase="completed", start_time=start_time)

            # Clean up progress file after a short delay (so status line can show completion)
            import asyncio

            async def delayed_cleanup():
                await asyncio.sleep(2)  # Show "completed" for 2 seconds
                self._cleanup_progress_file()

            asyncio.create_task(delayed_cleanup())

            # Return a concise completion summary
            if steps_ran == 0:
                return "No turns executed (session may already be completed)."

            return (
                f"Chatter collaboration completed {steps_ran} turn(s) in session '{session_id}'.\n"
                f"Final status: {session.status}\n"
                f"Total turns: {session.current_step}/{session.max_steps}\n\n"
                f"Last model: {last_model}\n"
                f"Last response: {last_response[:1000]}{'...' if len(last_response) > 1000 else ''}"
            )

        except Exception as e:
            logger.error(
                f"Collaboration execution failed for session {session_id}: {e}"
            )

            # Try to mark session as failed if it exists
            try:
                from ..config import get_settings

                settings = get_settings()
                project = Path(settings.logging.project_path or os.getcwd()).name

                collab_state = await self.session_cache.get_metadata(
                    project, "chatter_collaborate", session_id, "collab_state"
                )
                if collab_state:
                    collab_state["status"] = "failed"
                    await self.session_cache.set_metadata(
                        project,
                        "chatter_collaborate",
                        session_id,
                        "collab_state",
                        collab_state,
                    )
            except Exception:
                pass  # Don't let cleanup errors mask the original error

            # Clean up progress file on error
            self._cleanup_progress_file()

            return f"Collaboration error: {str(e)}"

    async def _get_or_create_session(
        self,
        project: str,
        session_id: str,
        objective: str,
        models: list[str],
        mode: Literal["round_robin", "orchestrator"],
        config: CollaborationConfig,
    ) -> CollaborationSession:
        """Get existing session or create new one."""

        # Try to load existing session from metadata
        existing_state = await self.session_cache.get_metadata(
            project, "chatter_collaborate", session_id, "collab_state"
        )

        if existing_state:
            logger.debug(f"Loaded existing session {session_id} from metadata")
            session = CollaborationSession.from_dict(existing_state)

            # Allow extending max_steps for continuation
            if config.max_steps > session.max_steps:
                logger.info(
                    f"Extending session {session_id} from {session.max_steps} to {config.max_steps} steps"
                )
                session.max_steps = config.max_steps
                # Reset status if it was completed but we're extending
                if session.status == "completed":
                    session.status = "active"
                    logger.info(
                        f"Reactivating completed session {session_id} for continuation"
                    )

                # Save the updated session immediately
                await self.session_cache.set_metadata(
                    project,
                    "chatter_collaborate",
                    session_id,
                    "collab_state",
                    session.to_dict(),
                )
                logger.info(
                    f"Saved extended session state: {session.current_step}/{session.max_steps}"
                )

            return session

        # Create new session
        logger.debug(f"Creating new collaboration session {session_id}")
        new_session = CollaborationSession(
            session_id=session_id,
            objective=objective,
            models=models,
            messages=[],
            current_step=0,
            mode=mode,
            max_steps=config.max_steps,
            status="active",
        )

        # Save new session as metadata
        await self.session_cache.set_metadata(
            project,
            "chatter_collaborate",
            session_id,
            "collab_state",
            new_session.to_dict(),
        )

        return new_session

    async def _execute_model_turn(
        self,
        session: CollaborationSession,
        whiteboard_info: dict,
        timeout: Optional[int] = None,
        context: Optional[list[str]] = None,
        priority_context: Optional[list[str]] = None,
    ) -> str:
        """Execute single model turn with whiteboard and file context.

        This method uses the critical executor vector_store_ids passthrough
        to provide models with access to the shared whiteboard, plus any
        additional context files specified.

        Args:
            session: Current collaboration session
            whiteboard_info: Whiteboard store information
            timeout: Optional timeout in seconds for this turn
            context: Optional list of file/directory paths for context
            priority_context: Optional list of priority file/directory paths
        """
        # Get next model based on orchestration mode
        if session.mode == "round_robin":
            next_model = session.models[session.current_step % len(session.models)]
        else:
            # For orchestrator mode, use first model as default
            # TODO: Implement smart orchestrator decision-making
            next_model = session.models[0] if session.models else ""

        logger.debug(f"Executing turn for {next_model} in session {session.session_id}")

        # Build instructions that reference the whiteboard
        instructions = self._build_collaboration_instructions(session, next_model)

        # Create unique sub-session ID to prevent history pollution
        sub_session_id = f"{session.session_id}__{next_model}"

        try:
            # Get model metadata (no mutation needed)
            model_metadata = self._get_tool_metadata(next_model)

            if timeout is not None:
                logger.debug(
                    f"Enforcing {timeout}s timeout for {next_model} in session {session.session_id}"
                )

            # Execute model with critical parameters:
            # - disable_history_record=True: Prevents pollution of project history
            # - disable_history_search=True: Prevents accessing outdated project context
            # - vector_store_ids: Provides access to shared whiteboard (critical passthrough)
            # - context/priority_context: File/directory paths for additional context
            # - unique sub-session ID: Isolates model's temporary session
            # - timeout: Enforced from CollaborationConfig via executor override
            response = await self.executor.execute(
                metadata=model_metadata,
                instructions=instructions,
                output_format="Contribute to the collaborative discussion. Use file_search to review the whiteboard if needed.",
                session_id=sub_session_id,
                disable_history_record=True,  # Critical: Prevent history pollution
                disable_history_search=True,  # Critical: Force focus on whiteboard only
                vector_store_ids=[
                    whiteboard_info["store_id"]
                ],  # Critical: Whiteboard access via passthrough
                context=context,  # File/directory context for collaboration
                priority_context=priority_context,  # Priority context files
                timeout=timeout,  # Pass timeout as kwarg for executor override
            )

            logger.debug(
                f"Successfully executed {next_model} for session {session.session_id}"
            )
            return response

        except Exception as e:
            logger.error(
                f"Model execution failed for {next_model} in session {session.session_id}: {e}"
            )

            # Return error message but don't crash the collaboration
            return f"Error from {next_model}: {str(e)}"

    def _build_collaboration_instructions(
        self, session: CollaborationSession, model_name: str
    ) -> str:
        """Build instructions for the model that reference the whiteboard."""

        instructions = f"""You are participating in a multi-model collaboration session.

**Collaboration Objective:** {session.objective}

**Your Role:** {model_name}
**Current Step:** {session.current_step + 1} of {session.max_steps}
**Mode:** {session.mode}
**Other Participants:** {', '.join([m for m in session.models if m != model_name])}

**Instructions:**
1. Use file_search to review the whiteboard conversation history
2. Consider previous contributions from other models and the user
3. Provide your unique perspective and analysis
4. Build on others' ideas constructively
5. Ask clarifying questions if needed
6. Keep your response focused and collaborative

The whiteboard contains the full conversation history. Use file_search to access it before responding."""

        return instructions

    def _get_tool_metadata(self, tool_name: str):
        """Get tool metadata for the given tool name."""
        from ..tools.registry import get_tool

        metadata = get_tool(tool_name)
        if metadata is None:
            raise ValueError(f"Tool {tool_name} not found in registry")

        return metadata

    def _write_progress_file(
        self,
        session: CollaborationSession,
        current_model: Optional[str] = None,
        phase: str = "collaborating",
        start_time: Optional[float] = None,
    ) -> None:
        """Write progress file for Claude Code status line display."""
        try:
            # Get project directory
            from ..config import get_settings

            settings = get_settings()
            project_path = Path(settings.logging.project_path or os.getcwd())

            # Create .claude directory if it doesn't exist
            claude_dir = project_path / ".claude"
            claude_dir.mkdir(exist_ok=True)

            # Calculate progress percentage
            if session.max_steps > 0:
                percent = int((session.current_step / session.max_steps) * 100)
            else:
                percent = 0

            # Calculate ETA if start_time provided
            eta_s = None
            if start_time and session.current_step > 0:
                elapsed = time.time() - start_time
                avg_time_per_step = elapsed / session.current_step
                remaining_steps = session.max_steps - session.current_step
                eta_s = int(avg_time_per_step * remaining_steps)

            # Create progress data
            progress_data = {
                "owner": "Chatter",
                "session_id": session.session_id,
                "phase": phase,
                "step": session.current_step,
                "total": session.max_steps,
                "percent": percent,
                "current_model": current_model,
                "mode": session.mode,
                "status": session.status,
                "updated_at": datetime.now().isoformat(),
                "eta_s": eta_s,
            }

            # Write to progress file
            progress_file = claude_dir / "chatter_progress.json"
            with open(progress_file, "w") as f:
                json.dump(progress_data, f, indent=2)

            logger.debug(f"Updated progress file: {progress_file}")

        except Exception as e:
            # Don't let progress file errors crash the collaboration
            logger.warning(f"Failed to write progress file: {e}")

    def _cleanup_progress_file(self) -> None:
        """Clean up progress file when collaboration completes."""
        try:
            from ..config import get_settings

            settings = get_settings()
            project_path = Path(settings.logging.project_path or os.getcwd())
            progress_file = project_path / ".claude" / "chatter_progress.json"

            if progress_file.exists():
                progress_file.unlink()
                logger.debug(f"Cleaned up progress file: {progress_file}")

        except Exception as e:
            logger.warning(f"Failed to cleanup progress file: {e}")

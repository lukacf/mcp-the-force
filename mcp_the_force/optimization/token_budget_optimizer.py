"""Token budget optimizer with iterative convergence."""

import logging
from typing import List, Optional, Tuple

from ..utils.token_counter import count_tokens
from ..utils.stable_list_cache import StableListCache
from .models import FileInfo, Plan, BudgetSnapshot
from .prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


class TokenBudgetOptimizer:
    """Optimizes token budget to fit prompts within model context windows."""

    def __init__(
        self,
        model_limit: int,
        fixed_reserve: int,
        session_id: str,
        context_paths: List[str],
        priority_paths: Optional[List[str]] = None,
        developer_prompt: str = "",
        instructions: str = "",
        output_format: str = "",
        project_name: str = "",
        tool_name: str = "",
    ):
        self.model_limit = model_limit
        self.fixed_reserve = fixed_reserve
        self.session_id = session_id
        self.context_paths = context_paths
        self.priority_paths = priority_paths or []
        self.developer_prompt = developer_prompt
        self.instructions = instructions
        self.output_format = output_format
        self.project_name = project_name
        self.tool_name = tool_name

        self.prompt_builder = PromptBuilder()
        self.max_iterations = 10

    async def optimize(self) -> Plan:
        """
        Multi-pass optimization to fit prompt within model limits.

        Returns:
            Plan with optimized file distribution and final prompt
        """
        logger.info(f"[OPTIMIZER] Starting optimization for session {self.session_id}")

        # Load session history and calculate its token cost
        session_history_tokens = 0
        session_messages = []

        if self.project_name and self.tool_name:
            try:
                from ..unified_session_cache import unified_session_cache
                import json

                history = await unified_session_cache.get_history(
                    self.project_name, self.tool_name, self.session_id
                )

                # Fallback for temp sessions: try to find under different project names
                if not history and self.session_id.startswith("temp-"):
                    logger.debug(
                        "[OPTIMIZER] No history found with current project, trying fallback lookup for temp session"
                    )
                    # Try to find the session by querying the database directly
                    from ..unified_session_cache import _get_instance

                    cache_instance = _get_instance()
                    rows = await cache_instance._execute_async(
                        "SELECT project, tool, history FROM unified_sessions WHERE session_id = ? AND tool = ? LIMIT 1",
                        (self.session_id, self.tool_name),
                    )
                    if rows:
                        actual_project, actual_tool, history_json = rows[0]
                        logger.debug(
                            f"[OPTIMIZER] Found temp session under project={actual_project}"
                        )
                        if history_json:
                            import orjson

                            history = orjson.loads(history_json)
                        else:
                            history = []

                if history:
                    session_messages = history
                    # Count exact tokens in session history using tiktoken
                    history_text = " ".join([json.dumps(msg) for msg in history])
                    session_history_tokens = count_tokens([history_text])
                    logger.info(
                        f"[OPTIMIZER] Session history: {len(history)} messages, {session_history_tokens:,} tokens"
                    )
            except Exception as e:
                logger.warning(f"[OPTIMIZER] Failed to load session history: {e}")
                session_history_tokens = 0
                session_messages = []

        # Use existing context builder to get initial split
        cache = StableListCache()

        # Calculate initial budget including session history overhead
        initial_budget = self.model_limit - self.fixed_reserve - session_history_tokens

        # Get initial file split from context builder - import here to match test mocking
        from ..utils.context_builder import build_context_with_stable_list

        inline_files, overflow_files, file_tree = await build_context_with_stable_list(
            context_paths=self.context_paths,
            session_id=self.session_id,
            cache=cache,
            token_budget=initial_budget,
            priority_context=self.priority_paths,
        )

        # Debug logging for the tuple issue
        logger.info(
            f"[OPTIMIZER] Initial split: {len(inline_files)} inline, {len(overflow_files)} overflow"
        )
        logger.debug(f"[OPTIMIZER] inline_files structure: {inline_files}")
        logger.debug(f"[OPTIMIZER] overflow_files structure: {overflow_files}")
        logger.debug(f"[OPTIMIZER] file_tree structure: {file_tree}")

        # Build initial prompt
        prompt = self.prompt_builder.build_prompt(
            instructions=self.instructions,
            output_format=self.output_format,
            inline_files=inline_files,
            all_files=self.context_paths,
            overflow_files=overflow_files,
        )

        # Start iterative optimization
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # Calculate complete prompt tokens
            complete_tokens = self.prompt_builder.calculate_complete_prompt_tokens(
                self.developer_prompt, prompt
            )

            snapshot = BudgetSnapshot(
                model_limit=self.model_limit,
                fixed_reserve=self.fixed_reserve,
                history_tokens=0,  # Included in developer_prompt
                overhead_tokens=0,  # Included in complete calculation
                available_budget=self.model_limit - self.fixed_reserve,
                prompt_tokens=complete_tokens,
            )

            logger.info(
                f"[OPTIMIZER][ITER_{iteration}] Prompt: {complete_tokens:,} tokens, "
                f"Limit: {self.model_limit:,}, Overage: {snapshot.overage:,}"
            )

            if snapshot.fits:
                logger.info(f"[OPTIMIZER] Converged in {iteration} iterations")
                break

            # Need to move files from inline to overflow
            if not inline_files:
                logger.error("[OPTIMIZER] No inline files left to move")
                break

            # Find movable files (non-priority)
            try:
                movable_files = [
                    (path, content, tokens)
                    for path, content, tokens in inline_files
                    if path not in self.priority_paths
                ]
            except ValueError as e:
                logger.error(f"[OPTIMIZER] Error unpacking inline_files tuples: {e}")
                logger.error(f"[OPTIMIZER] inline_files structure: {inline_files}")
                raise

            if not movable_files:
                logger.error(
                    "[OPTIMIZER] Only priority files remain, cannot optimize further"
                )
                break

            # Move largest files to free up enough tokens
            tokens_to_free = snapshot.overage + 1000  # Add buffer
            moved_files = self._move_largest_files(
                movable_files, overflow_files, tokens_to_free
            )

            # Update inline_files list
            try:
                moved_paths = {path for path, _, _ in moved_files}
                inline_files = [
                    (path, content, tokens)
                    for path, content, tokens in inline_files
                    if path not in moved_paths
                ]
            except ValueError as e:
                logger.error(
                    f"[OPTIMIZER] Error unpacking moved_files or inline_files: {e}"
                )
                logger.error(f"[OPTIMIZER] moved_files structure: {moved_files}")
                logger.error(f"[OPTIMIZER] inline_files structure: {inline_files}")
                raise

            logger.info(f"[OPTIMIZER] Moved {len(moved_files)} files to vector store")

            # Rebuild prompt with updated file distribution
            prompt = self.prompt_builder.build_prompt(
                instructions=self.instructions,
                output_format=self.output_format,
                inline_files=inline_files,
                all_files=self.context_paths,
                overflow_files=overflow_files,
            )

        # Final check
        final_tokens = self.prompt_builder.calculate_complete_prompt_tokens(
            self.developer_prompt, prompt
        )

        if final_tokens > self.model_limit:
            overage = final_tokens - self.model_limit
            raise RuntimeError(
                f"Failed to optimize prompt after {iteration} iterations. "
                f"Final: {final_tokens:,} tokens exceeds limit {self.model_limit:,} by {overage:,}"
            )

        # Create final plan
        inline_file_infos = [
            FileInfo(
                path=path,
                size=0,
                est_tokens=tokens,
                exact_tokens=tokens,
                priority=path in self.priority_paths,
            )
            for path, _, tokens in inline_files
        ]

        overflow_file_infos = [
            FileInfo(
                path=path, size=0, est_tokens=0, priority=path in self.priority_paths
            )
            for path in overflow_files
        ]

        # Build complete message list (dev prompt + session history + user prompt)
        messages = []

        # Add developer prompt if not already in session history
        if not session_messages or session_messages[0].get("role") != "developer":
            messages.append({"role": "developer", "content": self.developer_prompt})

        # Add session history
        messages.extend(session_messages)

        # Add current user message with optimized prompt
        messages.append({"role": "user", "content": prompt})

        plan = Plan(
            inline_files=inline_file_infos,
            overflow_files=overflow_file_infos,
            file_tree=file_tree,
            total_prompt_tokens=final_tokens,
            iterations=iteration,
            optimized_prompt=prompt,  # Store the final optimized prompt
            messages=messages,  # Complete message list including history
        )

        logger.info(
            f"[OPTIMIZER] Final plan: {len(plan.inline_files)} inline files, "
            f"{len(plan.overflow_files)} overflow files, {final_tokens:,} tokens"
        )

        return plan

    def _move_largest_files(
        self,
        movable_files: List[Tuple[str, str, int]],
        overflow_files: List[str],
        tokens_to_free: int,
    ) -> List[Tuple[str, str, int]]:
        """Move largest files to overflow until enough tokens are freed."""
        # Sort by token count descending
        sorted_files = sorted(movable_files, key=lambda x: x[2], reverse=True)

        moved_files = []
        tokens_freed = 0

        for file_path, content, file_tokens in sorted_files:
            if tokens_freed >= tokens_to_free:
                break

            # Add to overflow
            if file_path not in overflow_files:
                overflow_files.append(file_path)

            moved_files.append((file_path, content, file_tokens))

            # Include both content tokens AND wrapper token overhead when calculating freed tokens
            wrapper_tokens = self.prompt_builder.file_wrapper_tokens(file_path)
            total_freed = file_tokens + wrapper_tokens
            tokens_freed += total_freed

            logger.debug(
                f"[OPTIMIZER] Moved {file_path} ({file_tokens:,} content + {wrapper_tokens:,} wrapper = {total_freed:,} total tokens) to overflow"
            )

        return moved_files

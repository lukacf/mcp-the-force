"""Token budget optimization with proper architectural separation."""

import logging
import json
from typing import List, Optional, Tuple

from ..utils.token_counter import count_tokens
from ..utils.token_utils import file_wrapper_tokens
from .models import Plan, FileInfo
from .prompt_builder import PromptBuilder
from ..utils.stable_list_cache import StableListCache

logger = logging.getLogger(__name__)


def _extract_message_text(msg_content) -> str:
    """Extract text from message content, handling both string and list formats.

    OpenAI format: content is a string
    LiteLLM format: content is a list like [{"type": "text", "text": "..."}]
    """
    if isinstance(msg_content, str):
        return msg_content
    elif isinstance(msg_content, list):
        # Extract text from LiteLLM format
        text_parts = []
        for item in msg_content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        return "".join(text_parts)
    else:
        # Fallback for unknown formats
        return str(msg_content) if msg_content else ""


class TokenBudgetOptimizer:
    """
    Single authority for inline/overflow decisions.

    This class owns ALL decisions about which files go inline vs vector store.
    StableListCache is used purely for history tracking.
    """

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

    async def optimize(self) -> Plan:
        """
        Multi-pass optimization to fit prompt within model limits.
        Now owns ALL inline/overflow decisions every call.

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

        # Initialize history tracker (no decision making)
        cache = StableListCache()

        # Calculate available budget including session history overhead
        available_budget = (
            self.model_limit - self.fixed_reserve - session_history_tokens
        )
        logger.info(f"[OPTIMIZER] Available budget: {available_budget:,} tokens")

        # STEP 1: Gather all files from context paths
        from ..utils.fs import gather_file_paths_async

        # For context paths, we should allow files outside the project root
        all_file_paths = await gather_file_paths_async(
            self.context_paths, skip_safety_check=True
        )
        logger.info(f"[OPTIMIZER] Found {len(all_file_paths)} total files")

        # STEP 2: Get history information (no decisions)
        previous_inline = await cache.get_previous_inline_list(self.session_id)
        is_first_call = await cache.is_first_call(self.session_id)

        logger.info(f"[OPTIMIZER] Previous inline files: {len(previous_inline)}")
        logger.info(f"[OPTIMIZER] Is first call: {is_first_call}")

        # Get change status for all files
        changed_files, unchanged_files = await cache.get_file_change_status(
            self.session_id, all_file_paths
        )
        logger.info(
            f"[OPTIMIZER] Changed files: {len(changed_files)}, Unchanged: {len(unchanged_files)}"
        )

        # STEP 3: Make inline/overflow decisions (optimizer's job)

        # DECISION PHASE: Include all files that could be inline
        # - Previous inline files (for demotion decisions)
        # - Priority files (always considered)
        # - Changed files (need decisions)
        # - New files (promotion candidates)
        candidate_inline = set()

        if not is_first_call:
            # Include previous inline for decision-making (may demote some)
            candidate_inline.update(previous_inline)

        # Always include priority files in decisions
        candidate_inline.update(self.priority_paths)

        # Always include changed files in decisions
        candidate_inline.update(changed_files)

        # Convert to list and filter to files that actually exist
        candidate_inline_list = [
            path for path in candidate_inline if path in all_file_paths
        ]

        logger.info(f"[OPTIMIZER] Candidate inline files: {len(candidate_inline_list)}")

        # STEP 4: Token-based optimization

        # Import file loading here to match test mocking patterns
        from ..utils.context_loader import load_specific_files_async
        from ..utils.file_tree import build_file_tree_from_paths

        # Load all candidate files for decision-making
        inline_file_data = await load_specific_files_async(candidate_inline_list)

        # CRITICAL FIX: Only count tokens for files we'll SEND (delta), not all candidates
        files_to_send_this_turn = []
        if is_first_call:
            # First call: send all inline files
            files_to_send_this_turn = inline_file_data
        else:
            # Subsequent calls: only send changed files or newly promoted files
            files_to_send_this_turn = [
                file_data
                for file_data in inline_file_data
                if file_data[0] in changed_files  # Changed files must be re-sent
                # Note: newly promoted files will be handled later in optimization
            ]

        # Calculate tokens for ONLY files being sent this turn (no double-counting)
        send_token_cost = sum(tokens for _, _, tokens in files_to_send_this_turn)

        # Add XML wrapper tokens for each inline file
        from ..utils.token_utils import file_wrapper_tokens

        wrapper_token_cost = sum(
            file_wrapper_tokens(path) for path, _, _ in files_to_send_this_turn
        )
        send_token_cost += wrapper_token_cost

        # Build file tree (check if first call - only include tree on first call)
        file_tree = ""
        file_tree_tokens = 0

        if is_first_call:
            # Only include file tree on first session message
            overflow_paths = [
                path for path in all_file_paths if path not in candidate_inline_list
            ]
            file_tree = build_file_tree_from_paths(all_file_paths, overflow_paths)
            file_tree_tokens = count_tokens([file_tree])
            logger.info(f"[OPTIMIZER] File tree tokens: {file_tree_tokens:,}")
        else:
            # Subsequent calls: no tree, AI already has context
            logger.info("[OPTIMIZER] Skipping file tree - not first call")

        # Calculate total prompt tokens needed (NO double-counting!)
        base_prompt_tokens = count_tokens(
            [self.developer_prompt, self.instructions, self.output_format]
        )

        # session_history_tokens already includes unchanged inline files from previous messages
        # so we only add the cost of NEW files being sent this turn
        total_needed = (
            base_prompt_tokens
            + send_token_cost  # Only new/changed files, not unchanged ones
            + file_tree_tokens
            + session_history_tokens  # Already includes previous unchanged inline files
        )

        logger.info(
            f"[OPTIMIZER] Token breakdown: base={base_prompt_tokens}, "
            f"send_delta={send_token_cost}, tree={file_tree_tokens}, "
            f"history={session_history_tokens}, total={total_needed:,}"
        )

        # STEP 5: Make inline/overflow decisions and adjust if needed

        # Start with all candidates as potential inline
        potential_inline = inline_file_data[:]
        overflow_files = [
            path for path in all_file_paths if path not in candidate_inline_list
        ]

        # Check if we need to make adjustments
        if is_first_call:
            # First call: use traditional budget-based selection
            if total_needed > available_budget:
                # Over budget - demote files
                logger.warning(
                    f"[OPTIMIZER] Over budget by {total_needed - available_budget:,} tokens"
                )
                potential_inline, additional_overflow = (
                    self._demote_files_to_fit_budget(
                        potential_inline,
                        available_budget
                        - base_prompt_tokens
                        - file_tree_tokens
                        - session_history_tokens,
                    )
                )
                overflow_files.extend(additional_overflow)

        else:
            # Subsequent calls: we can keep more inline since unchanged files don't cost tokens
            # Only the send_delta counts against budget
            if total_needed > available_budget:
                # This should be rare since we're only sending changed files
                logger.warning(
                    f"[OPTIMIZER] Over budget by {total_needed - available_budget:,} tokens on subsequent call"
                )
                # Demote some changed files if necessary
                files_to_send_this_turn, additional_overflow = (
                    self._demote_files_to_fit_budget(
                        files_to_send_this_turn,
                        available_budget
                        - base_prompt_tokens
                        - file_tree_tokens
                        - session_history_tokens,
                    )
                )
                overflow_files.extend(additional_overflow)

        # Final inline decision (use the result from _demote_files_to_fit_budget)
        final_inline_files = potential_inline

        logger.info(
            f"[OPTIMIZER] After optimization: {len(final_inline_files)} inline, {len(overflow_files)} overflow"
        )

        if total_needed < available_budget * 0.8:  # Under 80% budget usage
            # Under budget - try to promote some overflow files
            remaining_budget = available_budget - total_needed
            logger.info(
                f"[OPTIMIZER] Under budget - {remaining_budget:,} tokens available for promotion"
            )

            # Load potential promotion candidates (smallest first for efficiency)
            promotable_paths = [
                path for path in overflow_files if path not in self.priority_paths
            ]
            if promotable_paths:
                # Sample some files to check (don't load all for performance)
                sample_size = min(50, len(promotable_paths))
                sample_paths = promotable_paths[:sample_size]
                sample_data = await load_specific_files_async(sample_paths)

                # Sort by token count (smallest first - more files fit)
                sample_data.sort(key=lambda x: x[2])

                promoted_tokens = 0
                for file_data in sample_data:
                    if promoted_tokens + file_data[2] <= remaining_budget:
                        final_inline_files.append(file_data)
                        promoted_tokens += file_data[2]
                        overflow_files.remove(file_data[0])
                    else:
                        break

                if promoted_tokens > 0:
                    logger.info(
                        f"[OPTIMIZER] Promoted {promoted_tokens:,} tokens worth of files"
                    )

        # STEP 6: Save the new inline decision to cache
        final_inline_paths = [file_data[0] for file_data in final_inline_files]
        await cache.save_stable_list(self.session_id, final_inline_paths)

        # Determine which files we're sending
        files_to_send = []
        if is_first_call:
            # First call: send all inline files
            files_to_send = final_inline_files
        else:
            # Subsequent calls: send only changed inline files
            files_to_send = [
                file_data
                for file_data in final_inline_files
                if file_data[0] in changed_files
            ]

        # Prepare sent file info for deferred cache update (after successful API call)
        files_to_update = []
        for file_path, _, _ in files_to_send:
            try:
                import os

                stat = os.stat(file_path)
                files_to_update.append(
                    (file_path, int(stat.st_size), int(stat.st_mtime_ns))
                )
            except OSError as e:
                logger.warning(f"Could not stat file {file_path} for cache update: {e}")

        # NOTE: We do NOT update the cache here anymore!
        # The cache will be updated in executor.py after successful API call

        # STEP 7: Build the optimized prompt
        prompt = self.prompt_builder.build_prompt(
            instructions=self.instructions,
            output_format=self.output_format,
            inline_files=files_to_send,  # Only files being sent in this message
            all_files=self.context_paths,
            overflow_files=overflow_files,
        )

        # Calculate tokens for complete message list (dev + session history + user)
        # Build the complete message list to get accurate token count
        temp_complete_messages = []
        if self.developer_prompt:
            temp_complete_messages.append(
                {"role": "developer", "content": self.developer_prompt}
            )
        temp_complete_messages.extend(session_messages)
        if prompt:
            temp_complete_messages.append({"role": "user", "content": prompt})

        # Count tokens for all messages that will be sent to API
        final_tokens = count_tokens(
            [_extract_message_text(msg["content"]) for msg in temp_complete_messages]
        )

        # CRITICAL: Check if final result exceeds available budget and demote if needed
        if final_tokens > available_budget:
            logger.warning(
                f"[OPTIMIZER] Final prompt {final_tokens:,} exceeds available budget {available_budget:,}, demoting files"
            )

            # Calculate how much we need to reduce (for logging/debugging)
            excess_tokens = final_tokens - available_budget
            logger.debug(f"[OPTIMIZER] Need to reduce by {excess_tokens:,} tokens")

            # Demote files until we fit (no arbitrary retry limit)
            retry_count = 0

            while final_tokens > available_budget and files_to_send:
                retry_count += 1

                # Remove largest files first, but skip priority files
                files_to_send.sort(
                    key=lambda x: x[2], reverse=True
                )  # Sort by tokens desc

                # Find the first non-priority file to demote
                demoted_file = None
                for i, file_data in enumerate(files_to_send):
                    if file_data[0] not in self.priority_paths:
                        demoted_file = files_to_send.pop(i)
                        break

                if demoted_file is None:
                    # All remaining files are priority files - cannot demote further
                    # This is a failure condition if we're still over budget
                    break

                overflow_files.append(demoted_file[0])  # Add to overflow

                # Deduplicate overflow_files to prevent any duplicate issues
                overflow_files = list(dict.fromkeys(overflow_files))

                # Log with total tokens saved (content + wrapper)
                total_saved = demoted_file[2] + file_wrapper_tokens(demoted_file[0])
                logger.info(
                    f"[OPTIMIZER] Demoted {demoted_file[0]} (saved {total_saved} tokens) - retry {retry_count}"
                )

                # Rebuild prompt and recalculate
                # Use the SAME all_files list we used the first time to avoid
                # ballooning the file_map tree with individual file paths
                prompt = self.prompt_builder.build_prompt(
                    instructions=self.instructions,
                    output_format=self.output_format,
                    inline_files=files_to_send,
                    all_files=self.context_paths,  # Keep original directory list constant
                    overflow_files=overflow_files,
                )

                # Calculate tokens for complete message list (dev + session history + user)
                temp_complete_messages = []
                if self.developer_prompt:
                    temp_complete_messages.append(
                        {"role": "developer", "content": self.developer_prompt}
                    )
                temp_complete_messages.extend(session_messages)
                if prompt:
                    temp_complete_messages.append({"role": "user", "content": prompt})

                final_tokens = count_tokens(
                    [
                        _extract_message_text(msg["content"])
                        for msg in temp_complete_messages
                    ]
                )

                logger.info(f"[OPTIMIZER] After demotion: {final_tokens:,} tokens")

            if final_tokens > available_budget:
                if files_to_send:
                    error_msg = f"Failed to optimize prompt: {final_tokens:,} tokens still exceeds available budget {available_budget:,} after {retry_count} retries"
                else:
                    error_msg = f"Failed to optimize prompt: {final_tokens:,} tokens still exceeds available budget {available_budget:,} - no more files to demote"
                logger.error(f"[OPTIMIZER] {error_msg}")
                raise RuntimeError(error_msg)

        logger.info(
            f"[PREDICTED_USAGE] Session {self.session_id}: {final_tokens:,} tokens predicted"
        )
        logger.info(
            f"[OPTIMIZER] Final plan: {len(files_to_send)} files to send, "
            f"{len(final_inline_paths)} total inline, {len(overflow_files)} overflow"
        )

        # Don't concatenate developer prompt - it's sent separately in messages
        optimized_prompt = prompt

        # Convert to FileInfo objects for the plan
        inline_file_infos = []
        for file_path, content, tokens in files_to_send:
            try:
                import os

                size = os.path.getsize(file_path)
                mtime = int(os.path.getmtime(file_path))
            except OSError:
                size = len(content.encode("utf-8"))
                mtime = 0

            inline_file_infos.append(
                FileInfo(
                    path=file_path,
                    content=content,
                    size=size,
                    tokens=tokens,
                    mtime=mtime,
                )
            )

        overflow_file_infos = []
        for file_path in overflow_files:
            try:
                import os

                size = os.path.getsize(file_path)
                mtime = int(os.path.getmtime(file_path))
            except OSError:
                size = 0
                mtime = 0

            overflow_file_infos.append(
                FileInfo(
                    path=file_path,
                    content="",  # Overflow files don't have content
                    size=size,
                    tokens=0,  # Will be in vector store
                    mtime=mtime,
                )
            )

        # Build complete message list (dev + history + user)
        complete_messages = []

        # Add developer prompt if provided
        if self.developer_prompt:
            complete_messages.append(
                {"role": "developer", "content": self.developer_prompt}
            )

        # Add session history
        complete_messages.extend(session_messages)

        # Add current user message (use only the user prompt part, not the combined optimized_prompt)
        if (
            prompt
        ):  # Changed from self.instructions to prompt to handle empty instructions case
            complete_messages.append(
                {
                    "role": "user",
                    "content": prompt,  # Use only the user prompt part (without developer prompt)
                }
            )

        # Return the optimization plan
        return Plan(
            inline_files=inline_file_infos,
            overflow_files=overflow_file_infos,
            file_tree=file_tree,
            total_prompt_tokens=final_tokens,
            iterations=1,  # New architecture doesn't need multiple iterations
            optimized_prompt=optimized_prompt,
            messages=complete_messages,  # Complete message list
            overflow_paths=[
                info.path for info in overflow_file_infos
            ],  # Add overflow paths for vector store
            sent_files_info=files_to_update,  # Deferred cache update info
        )

    def _demote_files_to_fit_budget(
        self, file_data_list: List[Tuple[str, str, int]], budget: int
    ) -> Tuple[List[Tuple[str, str, int]], List[str]]:
        """
        Demote files to fit within budget, prioritizing smaller files.

        Args:
            file_data_list: List of (path, content, tokens) tuples
            budget: Available token budget

        Returns:
            (remaining_files, demoted_paths) where:
            - remaining_files: Files that fit within budget
            - demoted_paths: Paths of files that were demoted
        """
        if not file_data_list:
            return [], []

        def _file_total_tokens(path: str, content_tokens: int) -> int:
            """Calculate total tokens including XML wrapper"""
            return content_tokens + file_wrapper_tokens(path)

        # Separate priority from non-priority files
        priority_files = []
        demotable_files = []

        for file_data in file_data_list:
            file_path = file_data[0]
            if file_path in self.priority_paths:
                priority_files.append(file_data)
            else:
                demotable_files.append(file_data)

        # Sort demotable files by TOTAL token count (smallest first to maximize files in context)
        demotable_files.sort(
            key=lambda fd: _file_total_tokens(fd[0], fd[2]), reverse=False
        )

        # Start with priority files (they always stay)
        remaining_files = priority_files[:]
        current_tokens = sum(
            _file_total_tokens(path, tokens) for path, _, tokens in priority_files
        )

        # Add demotable files while they fit
        demoted_paths = []
        for path, content, content_tokens in demotable_files:
            total_tokens = _file_total_tokens(path, content_tokens)
            if current_tokens + total_tokens <= budget:
                remaining_files.append((path, content, content_tokens))
                current_tokens += total_tokens
            else:
                demoted_paths.append(path)

        logger.info(f"Demoted {len(demoted_paths)} files to fit budget")
        return remaining_files, demoted_paths

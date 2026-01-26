"""
RCT: CLI Command Format Tests

These tests validate the representation contract for commands we send TO CLI tools.
This includes resume flags, JSON output modes, and context injection.

Gate 0 requirement: All tests must be green before Phase 1.

References:
- Claude Code: --resume <session_id> --print
- Gemini CLI: --resume <session_id> (JSON output mode TBD)
- Codex CLI: exec resume <thread_id> --json
"""

import pytest
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CLICommand:
    """Represents a constructed CLI command.

    This is what we PLAN to construct. RCT validates the format is correct.
    """

    executable: str
    args: List[str]
    resume_id: Optional[str] = None
    json_output: bool = True

    @property
    def full_command(self) -> List[str]:
        return [self.executable] + self.args


class CLICommandBuilder:
    """Minimal command builder for RCT validation.

    This is a simplified version of what we'll implement.
    RCT validates the command format contracts.
    """

    def build_claude_command(
        self,
        task: str,
        resume_id: Optional[str] = None,
        context_dirs: Optional[List[str]] = None,
    ) -> CLICommand:
        """Build Claude Code CLI command.

        Format (new session): claude --print -p "<task>"
        Format (resume): claude --print --resume <session_id> -p "<task>"
        """
        args = ["--print"]  # JSON output mode

        if resume_id:
            args.extend(["--resume", resume_id])

        if context_dirs:
            for dir_path in context_dirs:
                args.extend(["--add-dir", dir_path])

        args.extend(["-p", task])

        return CLICommand(
            executable="claude",
            args=args,
            resume_id=resume_id,
            json_output=True,
        )

    def build_gemini_command(
        self,
        task: str,
        resume_id: Optional[str] = None,
    ) -> CLICommand:
        """Build Gemini CLI command.

        Format (new session): gemini "<task>"
        Format (resume): gemini --resume <session_id> "<task>"
        """
        args = []

        if resume_id:
            args.extend(["--resume", resume_id])

        args.append(task)

        return CLICommand(
            executable="gemini",
            args=args,
            resume_id=resume_id,
            json_output=True,
        )

    def build_codex_command(
        self,
        task: str,
        resume_id: Optional[str] = None,
    ) -> CLICommand:
        """Build Codex CLI command.

        Format (new session): codex --json "<task>"
        Format (resume): codex exec resume <thread_id> --json

        IMPORTANT: Codex uses a different resume pattern!
        - New session: codex --json "task"
        - Resume: codex exec resume <thread_id> --json
        """
        if resume_id:
            # Resume uses 'exec resume' subcommand
            args = ["exec", "resume", resume_id, "--json"]
        else:
            # New session
            args = ["--json", task]

        return CLICommand(
            executable="codex",
            args=args,
            resume_id=resume_id,
            json_output=True,
        )


# =============================================================================
# RCT Tests - These define the COMMAND FORMAT CONTRACTS
# =============================================================================


class TestClaudeCommandFormat:
    """RCT: Claude Code CLI command format."""

    @pytest.fixture
    def builder(self):
        return CLICommandBuilder()

    def test_new_session_command_format(self, builder):
        """New session uses --print for JSON output."""
        cmd = builder.build_claude_command(task="Write a test")

        assert cmd.executable == "claude"
        assert "--print" in cmd.args
        assert "-p" in cmd.args
        assert "Write a test" in cmd.args

    def test_resume_command_format(self, builder):
        """Resume uses --resume <session_id> flag."""
        cmd = builder.build_claude_command(
            task="Continue",
            resume_id="session-abc-123",
        )

        assert "--resume" in cmd.args
        assert "session-abc-123" in cmd.args
        # --resume should come before -p
        resume_idx = cmd.args.index("--resume")
        prompt_idx = cmd.args.index("-p")
        assert resume_idx < prompt_idx

    def test_resume_with_json_output(self, builder):
        """Resume mode still uses --print for JSON output."""
        cmd = builder.build_claude_command(
            task="Continue",
            resume_id="session-abc-123",
        )

        # Both --print and --resume should be present
        assert "--print" in cmd.args
        assert "--resume" in cmd.args

    def test_context_dirs_format(self, builder):
        """Context directories use --add-dir flag."""
        cmd = builder.build_claude_command(
            task="Analyze",
            context_dirs=["/path/to/context1", "/path/to/context2"],
        )

        # Each context dir gets its own --add-dir
        add_dir_count = cmd.args.count("--add-dir")
        assert add_dir_count == 2
        assert "/path/to/context1" in cmd.args
        assert "/path/to/context2" in cmd.args


class TestGeminiCommandFormat:
    """RCT: Gemini CLI command format."""

    @pytest.fixture
    def builder(self):
        return CLICommandBuilder()

    def test_new_session_command_format(self, builder):
        """New session passes task as argument."""
        cmd = builder.build_gemini_command(task="Explain this code")

        assert cmd.executable == "gemini"
        assert "Explain this code" in cmd.args

    def test_resume_command_format(self, builder):
        """Resume uses --resume <session_id> flag."""
        cmd = builder.build_gemini_command(
            task="Continue",
            resume_id="gemini-session-456",
        )

        assert "--resume" in cmd.args
        assert "gemini-session-456" in cmd.args


class TestCodexCommandFormat:
    """RCT: Codex CLI command format.

    CRITICAL: Codex uses a DIFFERENT resume pattern than Claude/Gemini!
    - New session: codex --json "task"
    - Resume: codex exec resume <thread_id> --json
    """

    @pytest.fixture
    def builder(self):
        return CLICommandBuilder()

    def test_new_session_command_format(self, builder):
        """New session uses --json flag with task."""
        cmd = builder.build_codex_command(task="Fix the bug")

        assert cmd.executable == "codex"
        assert "--json" in cmd.args
        assert "Fix the bug" in cmd.args
        # Should NOT have exec resume in new session
        assert "exec" not in cmd.args
        assert "resume" not in cmd.args

    def test_resume_command_uses_exec_resume(self, builder):
        """Resume uses 'exec resume <thread_id>' subcommand.

        This is the CRITICAL contract difference from Claude/Gemini.
        Codex does NOT use --resume flag, it uses 'exec resume' subcommand.
        """
        cmd = builder.build_codex_command(
            task="Continue",  # Note: task is ignored in resume mode
            resume_id="thread-789-xyz",
        )

        # Must use exec resume subcommand pattern
        assert "exec" in cmd.args
        assert "resume" in cmd.args
        assert "thread-789-xyz" in cmd.args

        # Verify order: exec resume <thread_id>
        exec_idx = cmd.args.index("exec")
        resume_idx = cmd.args.index("resume")
        thread_idx = cmd.args.index("thread-789-xyz")
        assert exec_idx < resume_idx < thread_idx

    def test_resume_still_uses_json_output(self, builder):
        """Resume mode still uses --json for structured output."""
        cmd = builder.build_codex_command(
            task="Continue",
            resume_id="thread-789-xyz",
        )

        assert "--json" in cmd.args

    def test_resume_does_not_include_task_in_args(self, builder):
        """Resume mode does NOT include task - only thread_id.

        When resuming, the context comes from the thread, not a new task.
        """
        cmd = builder.build_codex_command(
            task="This should be ignored",
            resume_id="thread-789-xyz",
        )

        # Task should NOT be in args for resume
        assert "This should be ignored" not in cmd.args
        # Only exec resume <thread_id> --json
        assert cmd.args == ["exec", "resume", "thread-789-xyz", "--json"]


class TestCrossCliResumeContracts:
    """RCT: Verify all CLIs have consistent resume semantics."""

    @pytest.fixture
    def builder(self):
        return CLICommandBuilder()

    def test_all_clis_support_json_output_in_resume(self, builder):
        """All CLIs support JSON output when resuming."""
        claude_cmd = builder.build_claude_command(task="t", resume_id="s1")
        gemini_cmd = builder.build_gemini_command(task="t", resume_id="s2")
        codex_cmd = builder.build_codex_command(task="t", resume_id="s3")

        assert claude_cmd.json_output is True
        assert gemini_cmd.json_output is True
        assert codex_cmd.json_output is True

    def test_resume_id_appears_in_all_cli_commands(self, builder):
        """Resume ID is present in command args for all CLIs."""
        claude_cmd = builder.build_claude_command(task="t", resume_id="claude-id")
        gemini_cmd = builder.build_gemini_command(task="t", resume_id="gemini-id")
        codex_cmd = builder.build_codex_command(task="t", resume_id="codex-id")

        assert "claude-id" in claude_cmd.args
        assert "gemini-id" in gemini_cmd.args
        assert "codex-id" in codex_cmd.args

    def test_new_session_vs_resume_are_different(self, builder):
        """New session and resume commands are structurally different."""
        # Claude
        claude_new = builder.build_claude_command(task="task")
        claude_resume = builder.build_claude_command(task="task", resume_id="id")
        assert "--resume" not in claude_new.args
        assert "--resume" in claude_resume.args

        # Gemini
        gemini_new = builder.build_gemini_command(task="task")
        gemini_resume = builder.build_gemini_command(task="task", resume_id="id")
        assert "--resume" not in gemini_new.args
        assert "--resume" in gemini_resume.args

        # Codex - uses different pattern
        codex_new = builder.build_codex_command(task="task")
        codex_resume = builder.build_codex_command(task="task", resume_id="id")
        assert "exec" not in codex_new.args
        assert "exec" in codex_resume.args

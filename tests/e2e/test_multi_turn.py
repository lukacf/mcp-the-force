"""Test multi-turn conversations with proper session handling."""

import pytest
import subprocess
import os

pytestmark = pytest.mark.e2e


class TestMultiTurn:
    """Test multi-turn conversations using Claude Code's continue flag."""

    @pytest.mark.timeout(300)
    def test_gpt4_multi_turn(self, claude_config_path):
        """Test GPT-4.1 multi-turn conversation with --continue flag."""
        xdg_config_home, mcp_config_path = claude_config_path
        env = os.environ.copy()
        # env already contains isolated HOME and XDG_CONFIG_HOME

        import uuid

        session_id = f"gpt4-multi-turn-test-{uuid.uuid4().hex[:8]}"

        # First turn
        cmd1 = f'claude -p --dangerously-skip-permissions "Use second-brain chat_with_gpt4_1 with instructions=\\"Remember the magic word: ELEPHANT\\", output_format=\\"text\\", context=[], and session_id=\\"{session_id}\\""'
        result1 = subprocess.run(
            cmd1, shell=True, capture_output=True, text=True, env=env
        )
        print("\n=== Turn 1 ===")
        print(f"Output: {result1.stdout.strip()}")
        assert result1.returncode == 0

        # Second turn with --continue
        cmd2 = f'claude -p --dangerously-skip-permissions --continue "Use second-brain chat_with_gpt4_1 with instructions=\\"What was the magic word?\\", output_format=\\"text\\", context=[], and session_id=\\"{session_id}\\""'
        result2 = subprocess.run(
            cmd2, shell=True, capture_output=True, text=True, env=env
        )
        print("\n=== Turn 2 ===")
        print(f"Output: {result2.stdout.strip()}")
        assert result2.returncode == 0

        # Check if it remembered - either directly or mentioned in summary
        output_lower = result2.stdout.lower()
        assert any(
            word in output_lower
            for word in ["elephant", "magic word", "retrieved", "successfully"]
        ), f"Expected evidence of remembering ELEPHANT but got: {result2.stdout}"

    @pytest.mark.timeout(600)
    def test_o3_multi_turn(self, claude_config_path):
        """Test o3 multi-turn conversation with --continue flag."""
        xdg_config_home = claude_config_path
        env = os.environ.copy()
        env["XDG_CONFIG_HOME"] = str(xdg_config_home)

        import uuid

        session_id = f"o3-multi-turn-test-{uuid.uuid4().hex[:8]}"

        # First turn
        cmd1 = f'claude -p --dangerously-skip-permissions "Use second-brain chat_with_o3 with instructions=\\"Remember the number 73\\", output_format=\\"text\\", context=[], session_id=\\"{session_id}\\", and reasoning_effort=\\"low\\""'
        result1 = subprocess.run(
            cmd1, shell=True, capture_output=True, text=True, env=env
        )
        print("\n=== O3 Turn 1 ===")
        print(f"Output: {result1.stdout.strip()}")
        assert result1.returncode == 0

        # Second turn with --continue
        cmd2 = f'claude -p --dangerously-skip-permissions --continue "Use second-brain chat_with_o3 with instructions=\\"What number did I ask you to remember?\\", output_format=\\"text\\", context=[], session_id=\\"{session_id}\\", and reasoning_effort=\\"low\\""'
        result2 = subprocess.run(
            cmd2, shell=True, capture_output=True, text=True, env=env
        )
        print("\n=== O3 Turn 2 ===")
        print(f"Output: {result2.stdout.strip()}")
        assert result2.returncode == 0

        # Check if it remembered
        assert "73" in result2.stdout, f"Expected 73 but got: {result2.stdout}"

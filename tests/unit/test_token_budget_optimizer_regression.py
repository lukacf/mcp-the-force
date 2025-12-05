"""Regression tests for TokenBudgetOptimizer.

These tests verify that the optimizer correctly handles priority_context files
and other edge cases that caused production errors.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import tempfile
from pathlib import Path


@pytest.fixture
def temp_files():
    """Create temporary files for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test files
        context_file = Path(tmpdir) / "context.py"
        context_file.write_text("# Context file\nprint('hello')")

        priority_file = Path(tmpdir) / "priority.md"
        priority_file.write_text("# Priority Document\nThis is important content.")

        # Create a subdirectory with files
        subdir = Path(tmpdir) / "src"
        subdir.mkdir()
        src_file = subdir / "main.py"
        src_file.write_text("def main():\n    pass")

        yield {
            "tmpdir": tmpdir,
            "context_file": str(context_file),
            "priority_file": str(priority_file),
            "src_dir": str(subdir),
            "src_file": str(src_file),
        }


def create_mock_stable_cache():
    """Create a properly mocked StableListCache."""
    mock_cache_instance = MagicMock()
    mock_cache_instance.get_previous_inline_list = AsyncMock(return_value=set())
    mock_cache_instance.is_first_call = AsyncMock(return_value=True)
    mock_cache_instance.get_file_change_status = AsyncMock(return_value=(set(), set()))
    mock_cache_instance.set_inline_list = AsyncMock()
    mock_cache_instance.save_stable_list = AsyncMock()
    return mock_cache_instance


class TestPriorityContextInclusion:
    """Tests for priority_context file inclusion in optimization."""

    @pytest.mark.asyncio
    async def test_priority_paths_included_in_file_gathering(self, temp_files):
        """Priority paths should be included when gathering files.

        Regression test: priority_context files were being filtered out because
        they weren't gathered with context_paths. This caused models to report
        "source document was unavailable" even when priority_context was set.

        Bug was in TokenBudgetOptimizer.optimize():
        - Line 143-145: all_file_paths only gathered from context_paths
        - Line 182: priority_paths were added to candidate_inline
        - Line 188-190: But then filtered to files in all_file_paths
        - Result: priority files got filtered out!
        """
        from mcp_the_force.optimization.token_budget_optimizer import (
            TokenBudgetOptimizer,
        )

        # Mock StableListCache
        with patch(
            "mcp_the_force.optimization.token_budget_optimizer.StableListCache"
        ) as MockCache:
            MockCache.return_value = create_mock_stable_cache()

            optimizer = TokenBudgetOptimizer(
                model_limit=100_000,
                fixed_reserve=10_000,
                session_id="test-session",
                context_paths=[temp_files["src_dir"]],  # Only src directory
                priority_paths=[temp_files["priority_file"]],  # Priority file separate
                developer_prompt="Test prompt",
                instructions="Test instructions",
                output_format="text",
                project_name="",  # Empty to skip session history loading
                tool_name="",
            )

            plan = await optimizer.optimize()

            # The priority file should be in the inline files
            # This is the regression: before the fix, it would not be included
            # Note: inline_files contains FileInfo objects, not strings
            # Also macOS temp paths may have /private prefix
            inline_paths = [f.path for f in plan.inline_files]
            priority_path = temp_files["priority_file"]

            # Check if priority file is in the list (handle /private prefix)
            found = any(
                p.endswith(priority_path)
                or priority_path.endswith(p.lstrip("/private"))
                for p in inline_paths
            )
            assert found, (
                f"Priority file should be in inline_files. "
                f"Looking for: {priority_path}, Got: {inline_paths}"
            )

    @pytest.mark.asyncio
    async def test_priority_paths_only_without_context_paths(self, temp_files):
        """Optimizer should work when only priority_paths are provided."""
        from mcp_the_force.optimization.token_budget_optimizer import (
            TokenBudgetOptimizer,
        )

        with patch(
            "mcp_the_force.optimization.token_budget_optimizer.StableListCache"
        ) as MockCache:
            MockCache.return_value = create_mock_stable_cache()

            optimizer = TokenBudgetOptimizer(
                model_limit=100_000,
                fixed_reserve=10_000,
                session_id="test-session-2",
                context_paths=[],  # No context paths
                priority_paths=[temp_files["priority_file"]],  # Only priority
                developer_prompt="Test",
                instructions="Test",
                output_format="text",
                project_name="",
                tool_name="",
            )

            plan = await optimizer.optimize()

            # Priority file should still be included
            inline_paths = [f.path for f in plan.inline_files]
            priority_path = temp_files["priority_file"]
            found = any(
                p.endswith(priority_path)
                or priority_path.endswith(p.lstrip("/private"))
                for p in inline_paths
            )
            assert found, f"Priority file not found in {inline_paths}"

    @pytest.mark.asyncio
    async def test_both_context_and_priority_paths(self, temp_files):
        """Both context and priority files should be included."""
        from mcp_the_force.optimization.token_budget_optimizer import (
            TokenBudgetOptimizer,
        )

        with patch(
            "mcp_the_force.optimization.token_budget_optimizer.StableListCache"
        ) as MockCache:
            MockCache.return_value = create_mock_stable_cache()

            optimizer = TokenBudgetOptimizer(
                model_limit=100_000,
                fixed_reserve=10_000,
                session_id="test-session-3",
                context_paths=[temp_files["context_file"]],
                priority_paths=[temp_files["priority_file"]],
                developer_prompt="Test",
                instructions="Test",
                output_format="text",
                project_name="",
                tool_name="",
            )

            plan = await optimizer.optimize()

            # Both should be included
            inline_paths = [f.path for f in plan.inline_files]

            # Helper to check path inclusion (handles /private prefix on macOS)
            def path_in_list(path, paths):
                return any(
                    p.endswith(path) or path.endswith(p.lstrip("/private"))
                    for p in paths
                )

            assert path_in_list(
                temp_files["context_file"], inline_paths
            ), f"Context file not found in {inline_paths}"
            assert path_in_list(
                temp_files["priority_file"], inline_paths
            ), f"Priority file not found in {inline_paths}"


class TestEmptyContextHandling:
    """Tests for handling empty context scenarios."""

    @pytest.mark.asyncio
    async def test_empty_context_and_priority_paths(self):
        """Optimizer should handle both empty context and priority paths."""
        from mcp_the_force.optimization.token_budget_optimizer import (
            TokenBudgetOptimizer,
        )

        with patch(
            "mcp_the_force.optimization.token_budget_optimizer.StableListCache"
        ) as MockCache:
            MockCache.return_value = create_mock_stable_cache()

            optimizer = TokenBudgetOptimizer(
                model_limit=100_000,
                fixed_reserve=10_000,
                session_id="test-session-empty",
                context_paths=[],
                priority_paths=[],
                developer_prompt="Test",
                instructions="Test",
                output_format="text",
                project_name="",
                tool_name="",
            )

            plan = await optimizer.optimize()

            # Should return empty inline files without error
            assert plan.inline_files == []
            assert plan.overflow_files == []


class TestNonexistentPathHandling:
    """Tests for handling nonexistent file paths."""

    @pytest.mark.asyncio
    async def test_nonexistent_priority_path_handled_gracefully(self):
        """Nonexistent priority paths should not cause errors."""
        from mcp_the_force.optimization.token_budget_optimizer import (
            TokenBudgetOptimizer,
        )

        with patch(
            "mcp_the_force.optimization.token_budget_optimizer.StableListCache"
        ) as MockCache:
            MockCache.return_value = create_mock_stable_cache()

            optimizer = TokenBudgetOptimizer(
                model_limit=100_000,
                fixed_reserve=10_000,
                session_id="test-session-nonexistent",
                context_paths=[],
                priority_paths=["/nonexistent/path/file.txt"],
                developer_prompt="Test",
                instructions="Test",
                output_format="text",
                project_name="",
                tool_name="",
            )

            # Should not raise an exception
            plan = await optimizer.optimize()

            # Should gracefully handle the nonexistent file
            assert "/nonexistent/path/file.txt" not in plan.inline_files

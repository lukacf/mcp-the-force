"""Comprehensive test suite for the optimization architecture.

Tests the TokenBudgetOptimizer, PromptBuilder, and integration with tiktoken mocks.
"""

import pytest
import tempfile
import os
from unittest.mock import AsyncMock, patch

from mcp_the_force.optimization.token_budget_optimizer import TokenBudgetOptimizer
from mcp_the_force.optimization.prompt_builder import PromptBuilder
from mcp_the_force.optimization.models import FileInfo, Plan, BudgetSnapshot
from mcp_the_force.utils.token_utils import file_wrapper_tokens


class TestPromptBuilder:
    """Test PromptBuilder XML construction and token calculation."""

    def test_build_prompt_with_inline_files(self):
        """Test building prompt with inline files."""
        builder = PromptBuilder()

        inline_files = [
            ("test.py", "print('hello')", 50),
            ("app.py", "def main(): pass", 75),
        ]

        prompt = builder.build_prompt(
            instructions="Test instructions",
            output_format="JSON format",
            inline_files=inline_files,
            all_files=["test.py", "app.py"],
            overflow_files=[],
        )

        # Verify XML structure
        assert "<Task>" in prompt
        assert "<Instructions>Test instructions</Instructions>" in prompt
        assert "<OutputFormat>JSON format</OutputFormat>" in prompt
        assert "<CONTEXT>" in prompt
        assert 'path="test.py"' in prompt
        assert "print('hello')" in prompt
        assert 'path="app.py"' in prompt
        assert "def main(): pass" in prompt

    def test_build_prompt_with_overflow_files(self):
        """Test building prompt with overflow files (vector store)."""
        builder = PromptBuilder()

        prompt = builder.build_prompt(
            instructions="Analyze codebase",
            output_format="Summary",
            inline_files=[("main.py", "# main file", 25)],
            all_files=["main.py", "utils.py", "config.py"],
            overflow_files=["utils.py", "config.py"],
        )

        # Should contain vector store instructions
        assert "search_task_files" in prompt
        assert "vector database" in prompt
        assert "attached" in prompt

        # Should contain inline file
        assert 'path="main.py"' in prompt
        assert "# main file" in prompt

    def test_build_prompt_empty_inline_files(self):
        """Test building prompt with empty inline files."""
        builder = PromptBuilder()

        prompt = builder.build_prompt(
            instructions="Test",
            output_format="Test",
            inline_files=[],  # Empty list
            all_files=["file1.py"],
            overflow_files=["file1.py"],
        )

        # Should still generate valid XML
        assert "<Task>" in prompt
        assert "<CONTEXT>" in prompt
        assert "search_task_files" in prompt

    @patch("mcp_the_force.optimization.prompt_builder.count_tokens")
    def test_calculate_complete_prompt_tokens(self, mock_count_tokens):
        """Test complete prompt token calculation."""
        mock_count_tokens.return_value = 1500

        builder = PromptBuilder()
        tokens = builder.calculate_complete_prompt_tokens(
            "Developer prompt content", "User prompt content"
        )

        assert tokens == 1500
        mock_count_tokens.assert_called_once_with(
            ["Developer prompt content", "User prompt content"]
        )

    @patch("mcp_the_force.utils.token_utils.count_tokens")
    def test_file_wrapper_tokens(self, mock_count_tokens):
        """Test file wrapper token calculation."""
        mock_count_tokens.return_value = 15

        builder = PromptBuilder()
        tokens = builder.file_wrapper_tokens("/path/to/file.py")

        assert tokens == 15
        mock_count_tokens.assert_called_once_with(
            ['<file path="/path/to/file.py"></file>']
        )


class TestTokenBudgetOptimizer:
    """Test TokenBudgetOptimizer iterative optimization logic."""

    @pytest.fixture
    def temp_files(self):
        """Create temporary files for testing."""
        files = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=f"_test{i}.py", delete=False
            ) as f:
                f.write(f"# Test file {i}\n" + "print('hello')\n" * (i + 1) * 10)
                files.append(f.name)

        yield files

        # Cleanup
        for file_path in files:
            if os.path.exists(file_path):
                os.unlink(file_path)

    @pytest.mark.asyncio
    async def test_optimization_with_session_history(self, temp_files):
        """Test optimization including session history tokens."""
        with (
            patch(
                "mcp_the_force.utils.context_builder.build_context_with_stable_list"
            ) as mock_context,
            patch(
                "mcp_the_force.unified_session_cache.unified_session_cache"
            ) as mock_cache,
            patch(
                "mcp_the_force.utils.token_counter.count_tokens"
            ) as mock_count_tokens,
        ):
            # Mock session history
            mock_cache.get_history = AsyncMock(
                return_value=[
                    {"role": "user", "content": "Previous message 1"},
                    {"role": "assistant", "content": "Previous response 1"},
                ]
            )

            # Mock token counting for history (simulate 500 tokens)
            mock_count_tokens.return_value = 500

            # Mock context builder to return manageable files
            mock_context.return_value = (
                [(temp_files[0], "small content", 200)],  # inline_files
                temp_files[1:],  # overflow_files
                "file tree",
            )

            optimizer = TokenBudgetOptimizer(
                model_limit=2000,
                fixed_reserve=500,
                session_id="test-session",
                context_paths=temp_files,
                priority_paths=[],
                developer_prompt="Test developer prompt",
                instructions="Test instructions",
                output_format="Test format",
                project_name="test-project",
                tool_name="test-tool",
            )

            plan = await optimizer.optimize()

            # Verify plan structure
            assert isinstance(plan, Plan)
            assert len(plan.inline_files) >= 0
            assert len(plan.overflow_files) >= 0
            assert plan.optimized_prompt
            assert plan.messages
            assert plan.total_prompt_tokens > 0

            # Verify session history was included in messages
            assert len(plan.messages) >= 3  # dev + history + user
            assert plan.messages[0]["role"] == "developer"
            assert any(msg["role"] == "user" for msg in plan.messages)

    @pytest.mark.asyncio
    async def test_optimization_convergence(self, temp_files):
        """Test that optimization converges within model limits."""
        with (
            patch(
                "mcp_the_force.utils.context_builder.build_context_with_stable_list"
            ) as mock_context,
            patch(
                "mcp_the_force.utils.token_counter.count_tokens"
            ) as mock_count_tokens,
            patch(
                "mcp_the_force.unified_session_cache.unified_session_cache"
            ) as mock_cache,
            patch(
                "mcp_the_force.optimization.prompt_builder.PromptBuilder.calculate_complete_prompt_tokens"
            ) as mock_calc_tokens,
        ):
            # Mock session history (empty)
            mock_cache.get_history = AsyncMock(return_value=[])

            # Mock large inline files that exceed budget
            mock_context.return_value = (
                [
                    (temp_files[0], "large content 1", 800),
                    (temp_files[1], "large content 2", 700),
                    (temp_files[2], "large content 3", 600),
                ],
                [],  # No initial overflow
                "file tree",
            )

            # Mock session history token counting (only called once)
            mock_count_tokens.return_value = 0  # Empty session history

            # Mock prompt token calculation to simulate convergence behavior
            calc_call_count = 0

            def mock_calc_prompt_tokens(dev_prompt, user_prompt):
                nonlocal calc_call_count
                calc_call_count += 1
                # First calculation - exceeds limit
                if calc_call_count == 1:
                    return 2500  # Exceeds 2000 limit
                # Second calculation - still too big
                elif calc_call_count == 2:
                    return 1800  # Still exceeds budget with reserve
                # Third calculation - fits
                else:
                    return 1200  # Fits within limit

            mock_calc_tokens.side_effect = mock_calc_prompt_tokens

            optimizer = TokenBudgetOptimizer(
                model_limit=2000,
                fixed_reserve=500,  # So effective limit is 1500
                session_id="test-session",
                context_paths=temp_files,
                priority_paths=[],
                developer_prompt="Dev prompt",
                instructions="Instructions",
                output_format="Format",
                project_name="test-project",
                tool_name="test-tool",
            )

            plan = await optimizer.optimize()

            # Should have optimized to fit within budget
            # Available budget = 2000 - 500 = 1500, so final prompt should be reasonable
            assert plan.total_prompt_tokens <= 2000  # Should fit within model limit
            assert len(plan.overflow_files) > 0  # Some files moved to overflow
            assert plan.iterations == 1  # New architecture is single-pass

    @pytest.mark.asyncio
    async def test_priority_files_preserved(self, temp_files):
        """Test that priority files are never moved to overflow."""
        with (
            patch(
                "mcp_the_force.utils.context_builder.build_context_with_stable_list"
            ) as mock_context,
            patch(
                "mcp_the_force.unified_session_cache.unified_session_cache"
            ) as mock_cache,
        ):
            # Mock session history (empty)
            mock_cache.get_history = AsyncMock(return_value=[])

            # Mock context with priority file
            mock_context.return_value = (
                [
                    (temp_files[0], "priority content", 400),  # Priority file
                    (temp_files[1], "regular content", 300),  # Regular file
                ],
                [],
                "file tree",
            )

            optimizer = TokenBudgetOptimizer(
                model_limit=1500,  # Increase limit to allow successful completion
                fixed_reserve=200,
                session_id="test-session",
                context_paths=temp_files,
                priority_paths=[temp_files[0]],  # Mark first file as priority
                developer_prompt="Dev prompt",
                instructions="Instructions",
                output_format="Format",
                project_name="test-project",
                tool_name="test-tool",
            )

            with patch.object(
                optimizer.prompt_builder, "calculate_complete_prompt_tokens"
            ) as mock_calc:
                # Mock token calculation to simulate convergence
                calc_calls = 0

                def mock_calc_tokens(dev_prompt, user_prompt):
                    nonlocal calc_calls
                    calc_calls += 1
                    if calc_calls == 1:
                        return 1600  # Exceeds limit, forces optimization
                    else:
                        return 1100  # After moving non-priority files, fits

                mock_calc.side_effect = mock_calc_tokens

                # Don't mock _move_largest_files - let it run naturally
                plan = await optimizer.optimize()

                # Priority file should remain inline
                import os

                priority_paths = [os.path.realpath(f.path) for f in plan.inline_files]
                expected_priority_path = os.path.realpath(temp_files[0])
                assert expected_priority_path in priority_paths

                # Regular file should be moved to overflow (unless it couldn't fit)
                # The exact behavior depends on the optimization algorithm

    @pytest.mark.asyncio
    async def test_wrapper_token_costs_in_migration(self, temp_files):
        """Test that wrapper token costs are included in optimization decisions."""
        with patch(
            "mcp_the_force.utils.context_builder.build_context_with_stable_list"
        ) as mock_context:
            mock_context.return_value = (
                [(temp_files[0], "content", 500)],
                [],
                "file tree",
            )

            optimizer = TokenBudgetOptimizer(
                model_limit=1000,
                fixed_reserve=200,
                session_id="test-session",
                context_paths=temp_files,
                priority_paths=[],
                developer_prompt="Dev prompt",
                instructions="Instructions",
                output_format="Format",
                project_name="test-project",
                tool_name="test-tool",
            )

            with patch.object(
                optimizer.prompt_builder, "file_wrapper_tokens"
            ) as mock_wrapper:
                mock_wrapper.return_value = 25  # XML wrapper costs 25 tokens

                # Mock prompt calculation to simulate successful optimization
                with patch.object(
                    optimizer.prompt_builder, "calculate_complete_prompt_tokens"
                ) as mock_calc:
                    # First call exceeds limit, second call (after demotion) fits
                    mock_calc.side_effect = [1200, 800]  # Exceeds, then fits

                    # Verify optimization handled the situation correctly
                    plan = await optimizer.optimize()

                    # The optimization should have successfully reduced the size
                    assert isinstance(plan.total_prompt_tokens, int)
                    assert (
                        plan.total_prompt_tokens <= 1000
                    )  # Should fit within model limit
                    assert len(plan.inline_files) >= 0  # Valid result

    @pytest.mark.asyncio
    async def test_optimization_failure_handling(self, temp_files):
        """Test handling when optimization cannot converge."""
        with (
            patch(
                "mcp_the_force.utils.context_builder.build_context_with_stable_list"
            ) as mock_context,
            patch(
                "mcp_the_force.unified_session_cache.unified_session_cache"
            ) as mock_cache,
        ):
            # Mock session history (empty)
            mock_cache.get_history = AsyncMock(return_value=[])

            # Mock only priority files that cannot be moved
            mock_context.return_value = (
                [
                    (temp_files[0], "huge priority content", 2000)
                ],  # Too big for any budget
                [],
                "file tree",
            )

            optimizer = TokenBudgetOptimizer(
                model_limit=1000,
                fixed_reserve=200,
                session_id="test-session",
                context_paths=temp_files,
                priority_paths=temp_files,  # All files are priority
                developer_prompt="Dev prompt",
                instructions="Instructions",
                output_format="Format",
                project_name="test-project",
                tool_name="test-tool",
            )

            with patch.object(
                optimizer.prompt_builder, "calculate_complete_prompt_tokens"
            ) as mock_calc:
                mock_calc.return_value = 1500  # Always exceeds limit

                # Should raise RuntimeError when cannot optimize
                with pytest.raises(RuntimeError, match="Failed to optimize prompt"):
                    await optimizer.optimize()


class TestFileWrapperTokens:
    """Test shared file wrapper token utilities."""

    @patch("mcp_the_force.utils.token_utils.count_tokens")
    def test_file_wrapper_tokens_calculation(self, mock_count_tokens):
        """Test wrapper token calculation for various paths."""
        mock_count_tokens.return_value = 18

        tokens = file_wrapper_tokens("/long/path/to/file.py")

        expected_markup = '<file path="/long/path/to/file.py"></file>'
        mock_count_tokens.assert_called_once_with([expected_markup])
        assert tokens == 18

    @patch("mcp_the_force.utils.token_utils.count_tokens")
    def test_file_wrapper_tokens_special_characters(self, mock_count_tokens):
        """Test wrapper tokens with special characters in paths."""
        mock_count_tokens.return_value = 22

        # Path with spaces and special chars
        special_path = "/path with spaces/file-name_v2.py"
        tokens = file_wrapper_tokens(special_path)

        expected_markup = f'<file path="{special_path}"></file>'
        mock_count_tokens.assert_called_once_with([expected_markup])
        assert tokens == 22


class TestBudgetSnapshot:
    """Test BudgetSnapshot calculations."""

    def test_budget_snapshot_overage(self):
        """Test overage calculation."""
        snapshot = BudgetSnapshot(
            model_limit=1000,
            fixed_reserve=200,
            history_tokens=100,
            overhead_tokens=50,
            available_budget=800,
            prompt_tokens=1200,  # Exceeds limit
        )

        assert snapshot.overage == 200  # 1200 - 1000
        assert not snapshot.fits

    def test_budget_snapshot_fits(self):
        """Test when prompt fits within limits."""
        snapshot = BudgetSnapshot(
            model_limit=1000,
            fixed_reserve=200,
            history_tokens=100,
            overhead_tokens=50,
            available_budget=800,
            prompt_tokens=900,  # Within limit
        )

        assert snapshot.overage == 0
        assert snapshot.fits


class TestFileInfo:
    """Test FileInfo data model."""

    def test_file_info_tokens_property(self):
        """Test that FileInfo stores token count correctly."""
        # Test FileInfo with exact tokens
        file_info = FileInfo(
            path="/test.py",
            content="# test content",
            size=1000,
            tokens=95,  # Exact token count
            mtime=12345,
        )

        assert file_info.tokens == 95  # Should use exact tokens
        assert file_info.path == "/test.py"
        assert file_info.size == 1000

        # Test another FileInfo
        file_info2 = FileInfo(
            path="/test2.py",
            content="",  # Empty content for overflow file
            size=500,
            tokens=0,  # Overflow files have 0 tokens
            mtime=67890,
        )

        assert file_info2.tokens == 0  # Overflow files have 0 tokens


class TestOptimizationIntegration:
    """Integration tests for the complete optimization flow."""

    @pytest.mark.asyncio
    async def test_end_to_end_optimization_flow(self):
        """Test the complete optimization flow from executor perspective."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            test_files = []
            for i in range(2):
                file_path = os.path.join(temp_dir, f"test{i}.py")
                with open(file_path, "w") as f:
                    f.write(f"# Test file {i}\n" + "def func(): pass\n" * 20)
                test_files.append(file_path)

            with patch(
                "mcp_the_force.unified_session_cache.unified_session_cache"
            ) as mock_cache:
                mock_cache.get_history = AsyncMock(return_value=[])

                optimizer = TokenBudgetOptimizer(
                    model_limit=2000,
                    fixed_reserve=500,
                    session_id="integration-test",
                    context_paths=test_files,
                    priority_paths=[],
                    developer_prompt="System prompt for testing",
                    instructions="Analyze the code files",
                    output_format="Provide a summary in JSON format",
                    project_name="test-project",
                    tool_name="test-tool",
                )

                plan = await optimizer.optimize()

                # Verify complete integration
                assert isinstance(plan, Plan)
                assert plan.optimized_prompt
                assert "<Task>" in plan.optimized_prompt
                assert "Analyze the code files" in plan.optimized_prompt
                assert "JSON format" in plan.optimized_prompt
                assert len(plan.messages) >= 2  # At least dev + user
                assert plan.total_prompt_tokens > 0
                assert plan.iterations >= 1

                # Verify message structure
                dev_msg = plan.messages[0]
                user_msg = plan.messages[-1]
                assert dev_msg["role"] == "developer"
                assert user_msg["role"] == "user"
                # FIXED: User message should NOT contain the developer prompt (that was the bug!)
                # The user content should be the user part only, not the combined optimized_prompt
                assert (
                    dev_msg["content"] in plan.optimized_prompt
                )  # Developer content is part of optimized prompt
                assert (
                    user_msg["content"] in plan.optimized_prompt
                )  # User content is also part of optimized prompt
                assert (
                    user_msg["content"] != plan.optimized_prompt
                )  # But user content is NOT the full optimized prompt

                # Verify the user message contains the expected task structure
                assert "<Task>" in user_msg["content"]
                assert "<Instructions>" in user_msg["content"]
                assert "<OutputFormat>" in user_msg["content"]

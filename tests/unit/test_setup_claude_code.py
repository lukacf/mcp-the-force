"""Tests for setup_claude_code tool."""

import pytest
from unittest.mock import patch


class TestSetupClaudeCodeService:
    """Tests for SetupClaudeCodeService."""

    @pytest.fixture
    def temp_project_dir(self, tmp_path):
        """Create a temporary project directory."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        return project_dir

    @pytest.fixture
    def service(self):
        """Create service instance."""
        from mcp_the_force.local_services.setup_claude_code import (
            SetupClaudeCodeService,
        )

        return SetupClaudeCodeService()

    @pytest.mark.asyncio
    async def test_creates_agents_directory_if_not_exists(
        self, service, temp_project_dir
    ):
        """Should create .claude/agents/ directory if it doesn't exist."""
        with patch(
            "mcp_the_force.local_services.setup_claude_code.get_project_dir"
        ) as mock_get_project_dir:
            mock_get_project_dir.return_value = str(temp_project_dir)

            await service.execute()

            agents_dir = temp_project_dir / ".claude" / "agents"
            assert agents_dir.exists()
            assert agents_dir.is_dir()

    @pytest.mark.asyncio
    async def test_creates_force_runner_agent(self, service, temp_project_dir):
        """Should create the force-runner agent file."""
        with patch(
            "mcp_the_force.local_services.setup_claude_code.get_project_dir"
        ) as mock_get_project_dir:
            mock_get_project_dir.return_value = str(temp_project_dir)

            await service.execute()

            agent_file = temp_project_dir / ".claude" / "agents" / "force-runner.md"
            assert agent_file.exists()

    @pytest.mark.asyncio
    async def test_force_runner_agent_has_correct_structure(
        self, service, temp_project_dir
    ):
        """Force-runner agent should have YAML frontmatter and system prompt."""
        with patch(
            "mcp_the_force.local_services.setup_claude_code.get_project_dir"
        ) as mock_get_project_dir:
            mock_get_project_dir.return_value = str(temp_project_dir)

            await service.execute()

            agent_file = temp_project_dir / ".claude" / "agents" / "force-runner.md"
            content = agent_file.read_text()

            # Should have YAML frontmatter
            assert content.startswith("---")
            assert "name:" in content
            assert "description:" in content
            assert "tools:" in content
            # Should have The Force tools
            assert "mcp__the-force__work_with" in content
            assert "mcp__the-force__consult_with" in content

    @pytest.mark.asyncio
    async def test_returns_list_of_installed_agents(self, service, temp_project_dir):
        """Should return list of agents that were installed."""
        with patch(
            "mcp_the_force.local_services.setup_claude_code.get_project_dir"
        ) as mock_get_project_dir:
            mock_get_project_dir.return_value = str(temp_project_dir)

            result = await service.execute()

            assert "agents_installed" in result
            assert "force-runner" in result["agents_installed"]

    @pytest.mark.asyncio
    async def test_returns_agents_directory_path(self, service, temp_project_dir):
        """Should return the path where agents were installed."""
        with patch(
            "mcp_the_force.local_services.setup_claude_code.get_project_dir"
        ) as mock_get_project_dir:
            mock_get_project_dir.return_value = str(temp_project_dir)

            result = await service.execute()

            assert "agents_dir" in result
            assert ".claude/agents" in result["agents_dir"]

    @pytest.mark.asyncio
    async def test_overwrites_existing_agent_files(self, service, temp_project_dir):
        """Should overwrite existing agent files (for updates)."""
        with patch(
            "mcp_the_force.local_services.setup_claude_code.get_project_dir"
        ) as mock_get_project_dir:
            mock_get_project_dir.return_value = str(temp_project_dir)

            # Create existing agent with different content
            agents_dir = temp_project_dir / ".claude" / "agents"
            agents_dir.mkdir(parents=True)
            agent_file = agents_dir / "force-runner.md"
            agent_file.write_text("old content")

            await service.execute()

            # Should be overwritten with new content
            new_content = agent_file.read_text()
            assert new_content != "old content"
            assert "mcp__the-force__work_with" in new_content

    @pytest.mark.asyncio
    async def test_returns_restart_instruction(self, service, temp_project_dir):
        """Should return instruction to restart Claude Code."""
        with patch(
            "mcp_the_force.local_services.setup_claude_code.get_project_dir"
        ) as mock_get_project_dir:
            mock_get_project_dir.return_value = str(temp_project_dir)

            result = await service.execute()

            assert "message" in result
            assert "restart" in result["message"].lower()

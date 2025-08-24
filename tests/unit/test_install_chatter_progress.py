"""Tests for Chatter progress installer tool."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock

from mcp_the_force.tools.install_chatter_progress import InstallChatterProgress
from mcp_the_force.local_services.chatter_progress_installer import ChatterProgressInstaller


class TestInstallChatterProgressTool:
    """Test InstallChatterProgress tool definition."""
    
    def test_tool_has_correct_model_name(self):
        """Test tool has the expected model name."""
        assert InstallChatterProgress.model_name == "install_chatter_progress"
    
    def test_tool_has_description(self):
        """Test tool has a meaningful description."""
        assert InstallChatterProgress.description is not None
        assert len(InstallChatterProgress.description) > 50
        assert "progress display" in InstallChatterProgress.description.lower()
    
    def test_tool_uses_installer_service(self):
        """Test tool references the correct service class."""
        assert InstallChatterProgress.service_cls == ChatterProgressInstaller
        assert InstallChatterProgress.adapter_class is None
    
    def test_tool_has_required_parameters(self):
        """Test tool defines all expected parameters."""
        assert hasattr(InstallChatterProgress, 'action')
        assert hasattr(InstallChatterProgress, 'project_dir')
        assert hasattr(InstallChatterProgress, 'with_hooks')
        assert hasattr(InstallChatterProgress, 'dry_run')
    
    def test_tool_has_reasonable_timeout(self):
        """Test tool has appropriate timeout for installation tasks."""
        assert InstallChatterProgress.timeout == 30


class TestChatterProgressInstaller:
    """Test ChatterProgressInstaller service functionality."""
    
    @pytest.fixture
    def installer(self):
        """Create installer instance."""
        return ChatterProgressInstaller()
    
    @pytest.fixture 
    def temp_project(self):
        """Create temporary project directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            yield project_path
    
    @pytest.mark.asyncio
    async def test_install_dry_run(self, installer, temp_project):
        """Test installation in dry run mode."""
        
        with patch('mcp_the_force.local_services.chatter_progress_installer.get_settings') as mock_settings:
            mock_settings.return_value.logging.project_path = str(temp_project)
            
            result = await installer.execute(
                action="install",
                project_dir=str(temp_project), 
                dry_run=True
            )
            
            # Should describe what would be done without making changes
            assert "DRY RUN" in result
            assert "Created directories" in result
            assert "status line multiplexer" in result
            
            # No actual files should be created
            claude_dir = temp_project / ".claude"
            assert not claude_dir.exists()
    
    @pytest.mark.asyncio 
    async def test_install_creates_directories(self, installer, temp_project):
        """Test installation creates required directories."""
        
        with patch('mcp_the_force.local_services.chatter_progress_installer.get_settings') as mock_settings:
            mock_settings.return_value.logging.project_path = str(temp_project)
            
            result = await installer.execute(
                action="install",
                project_dir=str(temp_project),
                with_hooks=False  # Simpler test without hooks
            )
            
            # Should have created directories
            claude_dir = temp_project / ".claude"
            chatter_dir = claude_dir / "chatter"
            
            assert claude_dir.exists()
            assert chatter_dir.exists()
            assert "successfully" in result.lower()
    
    @pytest.mark.asyncio
    async def test_status_no_installation(self, installer, temp_project):
        """Test status command when nothing is installed."""
        
        with patch('mcp_the_force.local_services.chatter_progress_installer.get_settings') as mock_settings:
            mock_settings.return_value.logging.project_path = str(temp_project)
            
            result = await installer.execute(
                action="status",
                project_dir=str(temp_project)
            )
            
            assert "Chatter Progress Status" in result
            assert "not found" in result
    
    @pytest.mark.asyncio
    async def test_unknown_action(self, installer, temp_project):
        """Test error handling for unknown action."""
        
        result = await installer.execute(
            action="invalid_action",
            project_dir=str(temp_project)
        )
        
        assert "Unknown action" in result
        assert "Available: install, uninstall, repair, status" in result

    @pytest.mark.asyncio
    async def test_existing_status_line_detection(self, installer, temp_project):
        """Test detection of existing status line configuration."""
        
        # Create existing settings with status line
        claude_dir = temp_project / ".claude"
        claude_dir.mkdir(exist_ok=True)
        
        existing_settings = {
            "statusLine": {
                "type": "command",
                "command": "echo 'My Custom Status'"
            }
        }
        
        settings_file = claude_dir / "settings.json"
        with open(settings_file, "w") as f:
            json.dump(existing_settings, f)
            
        # Test detection
        existing_cmd = await installer._detect_existing_status_line(temp_project)
        assert existing_cmd == "echo 'My Custom Status'"
    
    @pytest.mark.asyncio
    async def test_settings_merging_preserves_existing(self, installer, temp_project):
        """Test that settings merging preserves existing configuration."""
        
        claude_dir = temp_project / ".claude" 
        claude_dir.mkdir(exist_ok=True)
        chatter_dir = claude_dir / "chatter"
        chatter_dir.mkdir(exist_ok=True)
        
        # Create existing settings
        existing_settings = {
            "customSetting": "preserve_me",
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "existing_matcher",
                        "hooks": [{"command": "existing_command"}]
                    }
                ]
            }
        }
        
        settings_file = claude_dir / "settings.local.json"
        with open(settings_file, "w") as f:
            json.dump(existing_settings, f)
            
        # Test installation
        await installer._update_settings_file(
            settings_file, chatter_dir, None, True, False
        )
        
        # Verify existing content preserved
        with open(settings_file) as f:
            updated_settings = json.load(f)
            
        assert updated_settings["customSetting"] == "preserve_me"
        assert len(updated_settings["hooks"]["PreToolUse"]) == 2  # Original + Chatter
        assert updated_settings["hooks"]["PreToolUse"][0]["matcher"] == "existing_matcher"
        
    @pytest.mark.asyncio
    async def test_script_templates_generate(self, installer):
        """Test that script templates generate correctly."""
        
        # Test status line mux template
        mux_script = installer._get_statusline_mux_template("echo 'Original'")
        assert "#!/bin/bash" in mux_script
        assert "Chatter Status Line Multiplexer" in mux_script
        assert "echo 'Original'" in mux_script
        
        # Test hook templates
        pre_hook = installer._get_pre_hook_template()
        assert "#!/bin/bash" in pre_hook
        assert "chatter_progress.json" in pre_hook
        
        post_hook = installer._get_post_hook_template()
        assert "#!/bin/bash" in post_hook
        assert "sleep 3" in post_hook
        
        stop_hook = installer._get_stop_hook_template()
        assert "#!/bin/bash" in stop_hook
        assert "rm -f" in stop_hook
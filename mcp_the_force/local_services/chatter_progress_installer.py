"""ChatterProgressInstaller - Automatic setup of hooks and status line for Chatter progress display."""

import json
import logging
import os
import stat
from pathlib import Path
from typing import Dict, Any, Optional
import shutil

logger = logging.getLogger(__name__)


class ChatterProgressInstaller:
    """Installs Chatter progress display components safely and non-destructively."""

    def __init__(self):
        """Initialize installer."""
        pass

    async def execute(
        self,
        action: str = "install",
        project_dir: Optional[str] = None,
        with_hooks: bool = True,
        dry_run: bool = False,
        **kwargs,
    ) -> str:
        """Execute installer action.

        Args:
            action: Action to perform ('install', 'uninstall', 'repair', 'status')
            project_dir: Project directory (defaults to current working directory)
            with_hooks: Whether to install hooks (default: True)
            dry_run: Show what would be done without making changes
            **kwargs: Additional parameters

        Returns:
            Status message describing what was done
        """

        # Determine project directory
        if project_dir:
            project_path = Path(project_dir).resolve()
        else:
            from ..config import get_settings

            settings = get_settings()
            project_path = Path(settings.logging.project_path or os.getcwd()).resolve()

        logger.info(f"Chatter progress installer - {action} in {project_path}")

        try:
            if action == "install":
                return await self._install(project_path, with_hooks, dry_run)
            elif action == "uninstall":
                return await self._uninstall(project_path, dry_run)
            elif action == "repair":
                return await self._repair(project_path, dry_run)
            elif action == "status":
                return await self._status(project_path)
            else:
                return f"Unknown action: {action}. Available: install, uninstall, repair, status"

        except Exception as e:
            logger.error(f"Chatter progress installer failed: {e}")
            return f"Error: {str(e)}"

    async def _install(
        self, project_path: Path, with_hooks: bool, dry_run: bool
    ) -> str:
        """Install Chatter progress components."""

        claude_dir = project_path / ".claude"
        chatter_dir = claude_dir / "chatter"
        settings_file = claude_dir / "settings.local.json"

        results = []

        # 1. Create directories
        if not dry_run:
            claude_dir.mkdir(exist_ok=True)
            chatter_dir.mkdir(exist_ok=True)
        results.append(f"✅ Created directories: {claude_dir}, {chatter_dir}")

        # 2. Install status line multiplexer
        existing_status_line = await self._detect_existing_status_line(project_path)
        mux_result = await self._install_status_line_mux(
            chatter_dir, existing_status_line, dry_run
        )
        results.append(mux_result)

        # 3. Install hooks if requested
        if with_hooks:
            hooks_result = await self._install_hooks(
                settings_file, chatter_dir, dry_run
            )
            results.append(hooks_result)
        else:
            results.append("⏭️  Skipped hooks installation (with_hooks=False)")

        # 4. Update settings.local.json
        settings_result = await self._update_settings_file(
            settings_file, chatter_dir, existing_status_line, with_hooks, dry_run
        )
        results.append(settings_result)

        # 5. Create README with usage instructions
        if not dry_run:
            with open(chatter_dir / "README.md", "w") as f:
                f.write(self._get_readme_content())
        results.append(f"📝 Created {chatter_dir}/README.md with usage instructions")

        if dry_run:
            results.insert(0, "🔍 DRY RUN - No changes made")
        else:
            results.insert(0, "🎉 Chatter progress components installed successfully!")

        results.append("")
        results.append("Next steps:")
        results.append("1. Restart Claude Code or run /hooks to review")
        results.append(
            "2. Try a Chatter collaboration - progress will appear in status line"
        )
        results.append(f"3. To disable: touch {chatter_dir}/disable_statusline")
        results.append(
            "4. To uninstall: call install_chatter_progress(action='uninstall')"
        )

        return "\\n".join(results)

    async def _detect_existing_status_line(self, project_path: Path) -> Optional[str]:
        """Detect existing status line configuration."""

        settings_files = [
            project_path / ".claude" / "settings.local.json",
            project_path / ".claude" / "settings.json",
            Path.home() / ".claude" / "settings.json",
        ]

        for settings_file in settings_files:
            if settings_file.exists():
                try:
                    with open(settings_file) as f:
                        settings = json.load(f)

                    if "statusLine" in settings:
                        status_config = settings["statusLine"]
                        if (
                            isinstance(status_config, dict)
                            and "command" in status_config
                        ):
                            cmd = status_config["command"]
                            # Skip our own Chatter scripts to avoid loops
                            if cmd and "chatter" not in str(cmd).lower():
                                return str(cmd) if cmd is not None else None
                        elif isinstance(status_config, str):
                            # Skip our own scripts
                            if "chatter" not in status_config.lower():
                                return status_config

                except Exception as e:
                    logger.warning(f"Failed to read {settings_file}: {e}")

        logger.debug("No existing status line found (or only Chatter scripts found)")
        return None

    async def _install_status_line_mux(
        self, chatter_dir: Path, existing_cmd: Optional[str], dry_run: bool
    ) -> str:
        """Install status line multiplexer script."""

        mux_script = chatter_dir / "statusline_mux.sh"

        script_content = self._get_statusline_mux_template(existing_cmd)

        if not dry_run:
            with open(mux_script, "w") as f:
                f.write(script_content)
            # Make executable
            mux_script.chmod(mux_script.stat().st_mode | stat.S_IEXEC)

        if existing_cmd:
            return f"✅ Created status line multiplexer (preserving existing: {existing_cmd})"
        else:
            return (
                "✅ Created status line multiplexer (no existing status line detected)"
            )

    async def _install_hooks(
        self, settings_file: Path, chatter_dir: Path, dry_run: bool
    ) -> str:
        """Install hook scripts."""

        # Create hook scripts
        hooks_created = []

        # PreToolUse hook script
        pre_hook = chatter_dir / "pre_chatter.sh"
        pre_content = self._get_pre_hook_template()
        if not dry_run:
            with open(pre_hook, "w") as f:
                f.write(pre_content)
            pre_hook.chmod(pre_hook.stat().st_mode | stat.S_IEXEC)
        hooks_created.append("pre_chatter.sh")

        # PostToolUse hook script
        post_hook = chatter_dir / "post_chatter.sh"
        post_content = self._get_post_hook_template()
        if not dry_run:
            with open(post_hook, "w") as f:
                f.write(post_content)
            post_hook.chmod(post_hook.stat().st_mode | stat.S_IEXEC)
        hooks_created.append("post_chatter.sh")

        # Stop hook script
        stop_hook = chatter_dir / "stop_chatter.sh"
        stop_content = self._get_stop_hook_template()
        if not dry_run:
            with open(stop_hook, "w") as f:
                f.write(stop_content)
            stop_hook.chmod(stop_hook.stat().st_mode | stat.S_IEXEC)
        hooks_created.append("stop_chatter.sh")

        return f"✅ Created hook scripts: {', '.join(hooks_created)}"

    async def _update_settings_file(
        self,
        settings_file: Path,
        chatter_dir: Path,
        existing_status_line: Optional[str],
        with_hooks: bool,
        dry_run: bool,
    ) -> str:
        """Update settings.local.json with Chatter configuration."""

        # Load existing settings
        settings = {}
        if settings_file.exists():
            try:
                with open(settings_file) as f:
                    settings = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read existing settings: {e}")

        # Create backup
        backup_file = settings_file.with_suffix(".json.bak")
        if settings_file.exists() and not dry_run:
            shutil.copy2(settings_file, backup_file)

        # Update status line to use multiplexer
        mux_path = "./.claude/chatter/statusline_mux.sh"
        settings["statusLine"] = {"type": "command", "command": mux_path}

        # Merge hooks if requested
        if with_hooks:
            if "hooks" not in settings:
                settings["hooks"] = {}

            # Add Chatter hooks without overwriting existing ones
            self._merge_chatter_hooks(settings["hooks"], chatter_dir)

        # Write updated settings
        if not dry_run:
            with open(settings_file, "w") as f:
                json.dump(settings, f, indent=2)

        status_msg = f"✅ Updated {settings_file}"
        if backup_file.exists():
            status_msg += f" (backup: {backup_file})"

        return status_msg

    def _merge_chatter_hooks(
        self, hooks_config: Dict[str, Any], chatter_dir: Path
    ) -> None:
        """Safely merge Chatter hooks into existing hooks configuration."""

        # PreToolUse hook for Chatter initialization
        if "PreToolUse" not in hooks_config:
            hooks_config["PreToolUse"] = []

        chatter_pre_hook = {
            "matcher": "mcp__the-force__group_think",
            "hooks": [
                {
                    "type": "command",
                    "command": "./.claude/chatter/pre_chatter.sh",
                    "timeout": 5,
                }
            ],
        }

        # Only add if not already present
        if not any(
            hook.get("matcher") == "mcp__the-force__group_think"
            for hook in hooks_config["PreToolUse"]
        ):
            hooks_config["PreToolUse"].append(chatter_pre_hook)

        # PostToolUse hook for Chatter cleanup
        if "PostToolUse" not in hooks_config:
            hooks_config["PostToolUse"] = []

        chatter_post_hook = {
            "matcher": "mcp__the-force__group_think",
            "hooks": [
                {
                    "type": "command",
                    "command": "./.claude/chatter/post_chatter.sh",
                    "timeout": 10,
                }
            ],
        }

        if not any(
            hook.get("matcher") == "mcp__the-force__group_think"
            for hook in hooks_config["PostToolUse"]
        ):
            hooks_config["PostToolUse"].append(chatter_post_hook)

        # Stop hook for cleanup on interruption
        if "Stop" not in hooks_config:
            hooks_config["Stop"] = []

        chatter_stop_hook = {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": "./.claude/chatter/stop_chatter.sh",
                    "timeout": 5,
                }
            ],
        }

        # Check if we already have a Chatter stop hook
        chatter_stop_exists = False
        for hook_group in hooks_config["Stop"]:
            for hook in hook_group.get("hooks", []):
                if "chatter" in hook.get("command", ""):
                    chatter_stop_exists = True
                    break

        if not chatter_stop_exists:
            hooks_config["Stop"].append(chatter_stop_hook)

    def _get_statusline_mux_template(self, existing_cmd: Optional[str]) -> str:
        """Generate status line multiplexer script template."""

        # Build the original status line section properly
        if existing_cmd:
            original_section = f"""# Get original status line
original_status=""
if command -v $(echo "{existing_cmd}" | cut -d' ' -f1) >/dev/null 2>&1; then
    original_status=$(echo "$input_json" | {existing_cmd})
fi"""
        else:
            original_section = '''# No original status line configured
original_status=""'''

        # Build the disabled section properly
        if existing_cmd:
            disabled_section = f"""    # Run original status line only
    echo "$input_json" | {existing_cmd}
    exit 0"""
        else:
            disabled_section = """    # No original status line to fall back to
    echo "Claude Code"
    exit 0"""

        return f"""#!/bin/bash

# Chatter Status Line Multiplexer  
# Preserves existing status line while adding Chatter collaboration progress

# Read JSON input from Claude Code
input_json=$(cat)

# Extract project directory
project_dir=$(echo "$input_json" | jq -r '.workspace.project_dir // .workspace.current_dir // "."')

# Check if Chatter is disabled
if [[ -f "$project_dir/.claude/chatter/disable_statusline" ]]; then
{disabled_section}
fi

# Check for Chatter progress file
progress_file="$project_dir/.claude/chatter_progress.json"
chatter_status=""

if [[ -f "$progress_file" ]]; then
    # Read Chatter progress
    owner=$(jq -r '.owner // "Chatter"' "$progress_file")
    phase=$(jq -r '.phase // "working"' "$progress_file")
    step=$(jq -r '.step // 0' "$progress_file")
    total=$(jq -r '.total // 1' "$progress_file")
    percent=$(jq -r '.percent // 0' "$progress_file")
    current_model=$(jq -r '.current_model // ""' "$progress_file")
    eta_s=$(jq -r '.eta_s // null' "$progress_file")
    
    # Format ETA
    eta_text=""
    if [[ "$eta_s" != "null" && "$eta_s" -gt 0 ]]; then
        if [[ "$eta_s" -lt 60 ]]; then
            eta_text=" (ETA ${{eta_s}}s)"
        else
            eta_m=$((eta_s / 60))
            eta_text=" (ETA ${{eta_m}}m)"
        fi
    fi
    
    # Format model name (short)
    model_short=""
    if [[ -n "$current_model" ]]; then
        model_short=$(echo "$current_model" | sed 's/chat_with_//' | sed 's/gpt/GPT-/' | sed 's/gemini3/Gemini/' | sed 's/claude41/Claude/' | sed 's/claude45/Claude/')
    fi
    
    # Build Chatter status
    chatter_status="[$owner] $step/$total • $percent% • $model_short $phase$eta_text"
fi

{original_section}

# Combine status lines
if [[ -n "$chatter_status" && -n "$original_status" ]]; then
    echo "$original_status | $chatter_status"
elif [[ -n "$chatter_status" ]]; then
    echo "$chatter_status"
elif [[ -n "$original_status" ]]; then
    echo "$original_status"
else
    # Fallback status
    model=$(echo "$input_json" | jq -r '.model // "Claude"')
    cost=$(echo "$input_json" | jq -r '.cost.total_cost_usd // 0')
    echo "[$model] Ready • \\$$(printf \"%.3f\" \"$cost\")"
fi
"""

    def _get_pre_hook_template(self) -> str:
        """Generate PreToolUse hook script."""

        return """#!/bin/bash

# Chatter PreToolUse Hook - Initialize progress tracking

# Read hook input from stdin
hook_input=$(cat)

# Extract project directory
project_dir=$(echo "$hook_input" | jq -r '.projectDir // "."')

# Create progress file for Chatter initialization
mkdir -p "$project_dir/.claude"

echo '{
  "owner": "Chatter",
  "phase": "initializing",
  "step": 0,
  "total": 1,
  "percent": 0,
  "status": "starting",
  "updated_at": "'$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)'"
}' > "$project_dir/.claude/chatter_progress.json"

# Log initialization (will appear in transcript with Ctrl+R)
echo "Chatter progress tracking initialized" >&2
"""

    def _get_post_hook_template(self) -> str:
        """Generate PostToolUse hook script."""

        return """#!/bin/bash

# Chatter PostToolUse Hook - Clean up progress file after completion

# Read hook input from stdin
hook_input=$(cat)

# Extract project directory
project_dir=$(echo "$hook_input" | jq -r '.projectDir // "."')

# Delay cleanup to show completion status briefly
sleep 3

# Remove progress file
rm -f "$project_dir/.claude/chatter_progress.json"

# Log cleanup
echo "Chatter progress tracking cleaned up" >&2
"""

    def _get_stop_hook_template(self) -> str:
        """Generate Stop hook script."""

        return """#!/bin/bash

# Chatter Stop Hook - Clean up progress on interruption

# Read hook input from stdin  
hook_input=$(cat)

# Extract project directory
project_dir=$(echo "$hook_input" | jq -r '.projectDir // "."')

# Remove progress file immediately on stop
rm -f "$project_dir/.claude/chatter_progress.json"
"""

    async def _uninstall(self, project_path: Path, dry_run: bool) -> str:
        """Uninstall Chatter progress components."""

        results = []
        claude_dir = project_path / ".claude"
        chatter_dir = claude_dir / "chatter"
        settings_file = claude_dir / "settings.local.json"

        # Remove chatter directory
        if chatter_dir.exists():
            if not dry_run:
                shutil.rmtree(chatter_dir)
            results.append(f"✅ Removed Chatter scripts: {chatter_dir}")
        else:
            results.append("ℹ️  No Chatter directory found")

        # Restore original settings if backup exists
        backup_file = settings_file.with_suffix(".json.bak")
        if backup_file.exists():
            if not dry_run:
                shutil.move(backup_file, settings_file)
            results.append("✅ Restored original settings from backup")
        elif settings_file.exists():
            # Remove Chatter entries from settings
            if not dry_run:
                await self._remove_chatter_from_settings(settings_file)
            results.append("✅ Removed Chatter entries from settings")

        if dry_run:
            results.insert(0, "🔍 DRY RUN - No changes made")
        else:
            results.insert(0, "🗑️  Chatter progress components uninstalled")

        results.append("")
        results.append("Restart Claude Code to see changes")

        return "\\n".join(results)

    async def _remove_chatter_from_settings(self, settings_file: Path) -> None:
        """Remove Chatter entries from settings file."""

        try:
            with open(settings_file) as f:
                settings = json.load(f)

            # Remove status line if it points to our mux
            if "statusLine" in settings:
                status_line = settings["statusLine"]
                if isinstance(status_line, dict):
                    command = status_line.get("command", "")
                    if "chatter" in command:
                        del settings["statusLine"]

            # Remove Chatter hooks
            if "hooks" in settings:
                for event in ["PreToolUse", "PostToolUse", "Stop"]:
                    if event in settings["hooks"]:
                        # Remove hooks that reference chatter
                        settings["hooks"][event] = [
                            hook
                            for hook in settings["hooks"][event]
                            if not any(
                                "chatter" in h.get("command", "")
                                for h in hook.get("hooks", [])
                            )
                        ]

            # Write updated settings
            with open(settings_file, "w") as f:
                json.dump(settings, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to remove Chatter from settings: {e}")

    async def _repair(self, project_path: Path, dry_run: bool) -> str:
        """Repair installation (re-detect original status line)."""

        # Re-run installation with current detection
        return await self._install(project_path, with_hooks=True, dry_run=dry_run)

    async def _status(self, project_path: Path) -> str:
        """Show current installation status."""

        claude_dir = project_path / ".claude"
        chatter_dir = claude_dir / "chatter"
        settings_file = claude_dir / "settings.local.json"

        results = [f"Chatter Progress Status for: {project_path}"]
        results.append("")

        # Check directories
        if chatter_dir.exists():
            scripts = list(chatter_dir.glob("*.sh"))
            results.append(f"✅ Chatter directory exists with {len(scripts)} scripts")
        else:
            results.append("❌ Chatter directory not found")

        # Check settings
        if settings_file.exists():
            try:
                with open(settings_file) as f:
                    settings = json.load(f)
                if "statusLine" in settings:
                    results.append("✅ Status line configuration found")
                if "hooks" in settings:
                    results.append("✅ Hooks configuration found")
            except Exception:
                results.append("⚠️  Settings file exists but couldn't be read")
        else:
            results.append("❌ No settings.local.json found")

        # Check if disabled
        disable_file = chatter_dir / "disable_statusline"
        if disable_file.exists():
            results.append("⏸️  Progress display disabled")
        else:
            results.append("🟢 Progress display enabled")

        return "\\n".join(results)

    def _get_readme_content(self) -> str:
        """Generate README content for Chatter directory."""

        return """# Chatter Progress Display

This directory contains scripts for displaying real-time collaboration progress in Claude Code's status line.

## Files:
- `statusline_mux.sh` - Status line multiplexer (preserves existing status line)
- `pre_chatter.sh` - Initializes progress tracking when Chatter starts
- `post_chatter.sh` - Cleans up progress file when Chatter completes
- `stop_chatter.sh` - Cleans up progress on interruption

## Usage:
- Progress automatically appears in Claude Code status line during collaborations
- Shows: [Chatter] 3/7 • 43% • GPT-5 thinking (ETA 2m)

## Control:
- Disable: `touch disable_statusline` 
- Uninstall: Call `install_chatter_progress(action="uninstall")`
- Repair: Call `install_chatter_progress(action="repair")`

## Technical Details:
- Progress data stored in `.claude/chatter_progress.json`
- Status line refreshes automatically during Claude Code message updates
- Scripts are fast and exit quickly to avoid blocking
- All changes are project-scoped (doesn't affect global Claude Code settings)
"""
